"""
WAF Classifier — File Merger Blueprint
Merges 3 JIRA export files (Epic, Feature, Story) into the canonical WAF import format.

Two-phase flow:
  1. POST /api/merge/preview   — parse files, return per-file suggested mappings
                                  + sample rows so the user can confirm what each
                                  column means. DataFrames cached in memory keyed
                                  by token.
  2. POST /api/merge/process   — run the merge with the user-confirmed mappings,
                                  return stats + preview + issues + per-row status.

Join rules:
  Epic ↔ Feature  — joined by Epic Name (case-insensitive)
  Feature ↔ Story — joined by Feature Name (case-insensitive)

Per-row status flags drive analysis filtering:
  - complete         → ready for AI analysis
  - missing_feature  → story has no Feature link OR it doesn't resolve
  - missing_epic     → Feature resolves but its Epic Name doesn't
Plus a non-blocking flag:
  - missing_waf      → row's epic has no WAF set (informational only)

WAF field on the Epic file is in the format "ORANGE - Enterprise Strategic Priority".
It is split on " - " to derive WAF Color (left) and WAF Category (right).
"""

import io
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime

import pandas as pd
from flask import Blueprint, request, jsonify, send_file

merge_bp = Blueprint("merge_bp", __name__)

# Import alias normalizer — used to map variant names to canonical WAF categories
try:
    from waf_core import normalize_waf_category as _normalize_waf
except ImportError:
    def _normalize_waf(val, **_):
        return (val, False, val)

# In-memory store: token -> {epic_df, feature_df, story_df, has_*, created_at, merged_rows?}
_merge_store = {}

# How long preview/merge state lives before it's GC'd (seconds)
_STORE_TTL = 60 * 60  # 1 hour

# ── Known WAF colors ───────────────────────────────────────────────────────────
KNOWN_COLORS = {"GRAY", "BLACK", "RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE", "TEAL"}

# ── Target fields exposed to the UI mapping picker ─────────────────────────────
# Each field declares: key (internal), label (UI), required (per-file), keywords
# (auto-suggest hints).  The UI shows a dropdown per field, populated with the
# uploaded file's column headers, pre-selected from `suggested_mappings`.

EPIC_FIELDS = [
    {"key": "id_col",         "label": "Epic Id",     "required": False, "keywords": ["epic id", "jira saas epic", "epic#", "epic key", "epic number"]},
    {"key": "name_col",       "label": "Epic Name",   "required": True,  "keywords": ["epic name", "epic summary", "epic title", "summary"]},
    {"key": "desc_col",       "label": "Epic Desc",   "required": False, "keywords": ["epic description", "epic desc"]},
    {"key": "block_col",      "label": "Block",       "required": False, "keywords": ["block", "program/org", "program org", "org block"]},
    {"key": "waf_col",        "label": "WAF",         "required": True,  "keywords": ["work alignment framework", "work alignment"]},
    {"key": "run_change_col", "label": "Run/Change",  "required": False, "keywords": ["run/change", "run or change", "run change", "run_change"]},
]

FEATURE_FIELDS = [
    {"key": "id_col",          "label": "Feature Id",          "required": False, "keywords": ["feature id", "jira saas feature", "feature key"]},
    {"key": "name_col",        "label": "Feature Name",        "required": True,  "keywords": ["feature name", "feature summary", "summary"]},
    {"key": "desc_col",        "label": "Feature Desc",        "required": False, "keywords": ["feature description", "feature desc"]},
    {"key": "epic_name_col",   "label": "Epic Name (join key)", "required": True, "keywords": ["epic name", "parent epic", "epic link", "initiative"]},
    {"key": "tot_col",         "label": "Team of Teams",       "required": False, "keywords": ["team of teams", "team_of_teams"]},
    {"key": "pi_col",          "label": "PI Name",             "required": False, "keywords": ["pi name", "pi number", "planning interval"]},
]

STORY_FIELDS = [
    {"key": "id_col",            "label": "Story Id",               "required": False, "keywords": ["story id", "story#", "story number", "issue key"]},
    {"key": "name_col",          "label": "Story Name",             "required": True,  "keywords": ["story name", "summary", "title"]},
    {"key": "desc_col",          "label": "Story Desc",             "required": False, "keywords": ["story desc", "story description", "description"]},
    {"key": "feature_name_col",  "label": "Feature Name (join key)", "required": True, "keywords": ["feature name", "parent feature", "feature link"]},
    {"key": "points_col",        "label": "Story Points",           "required": False, "keywords": ["story points", "story_points", "points", "estimate"]},
    {"key": "team_col",          "label": "Assigned Teams",         "required": False, "keywords": ["assigned teams", "assigned team", "teams", "team"]},
]

OUTPUT_COLUMNS = [
    "PI Name",
    "Epic Id", "Epic Name", "Epic Desc", "Block",
    "WAF", "WAF Color", "WAF Category", "Run/Change",
    "Feature Id", "Feature Name", "Feature Desc", "Team of Teams",
    "Story Id", "Story Name", "Story Desc", "Story Points", "Assigned Teams",
    "Status",   # complete | missing_feature | missing_epic | missing_waf (extra info column)
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gc_store():
    """Drop entries older than TTL — keeps the in-memory store from growing unbounded."""
    cutoff = time.time() - _STORE_TTL
    stale = [t for t, v in _merge_store.items() if v.get("created_at", 0) < cutoff]
    for t in stale:
        _merge_store.pop(t, None)


def _suggest_mapping(headers, fields):
    """
    Given a list of column headers and a list of field defs, return a dict
    {field_key: matched_header_or_empty_string}, with each header claimed at most
    once (priority by field order, keyword order).
    """
    h_map = {h.lower().strip(): h for h in headers}
    claimed = set()
    out = {}
    for f in fields:
        match = ""
        for kw in f["keywords"]:
            kw_lower = kw.lower()
            for h_lower, h_orig in h_map.items():
                if h_orig in claimed:
                    continue
                if kw_lower in h_lower:
                    match = h_orig
                    break
            if match:
                break
        out[f["key"]] = match
        if match:
            claimed.add(match)
    return out


_RUN_CHANGE_SUFFIX = re.compile(r'\s*\((run|change)\)\s*$', re.IGNORECASE)

def extract_run_change_from_name(name):
    """Strip a trailing '(Run)' or '(Change)' from an epic name.
    Returns (clean_name, run_change_value)."""
    m = _RUN_CHANGE_SUFFIX.search(name)
    if m:
        clean = _RUN_CHANGE_SUFFIX.sub("", name).strip()
        return clean, m.group(1).capitalize()
    return name, ""


def parse_waf_field(waf_value):
    """Parse 'ORANGE - Enterprise Strategic Priority' → (color, category)."""
    if not waf_value or (isinstance(waf_value, float) and pd.isna(waf_value)):
        return "", ""
    val = str(waf_value).strip()
    if " - " in val:
        parts = val.split(" - ", 1)
        color_candidate = parts[0].strip().upper()
        category_part   = parts[1].strip()
        if color_candidate in KNOWN_COLORS:
            return color_candidate, category_part
        normalized = _normalize_waf(category_part)[0] if category_part else ""
        return "", normalized or category_part
    normalized = _normalize_waf(val)[0] if val else ""
    return "", normalized or val


def read_file(file_storage):
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[-1].lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise ValueError(f"Unsupported file type '{ext}'. Upload CSV or Excel.")
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(file_storage)
    try:
        return pd.read_csv(file_storage, encoding="utf-8")
    except UnicodeDecodeError:
        file_storage.seek(0)
        return pd.read_csv(file_storage, encoding="latin-1")


def safe_str(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def make_filename(job_name, token):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    if job_name:
        safe = re.sub(r"[^\w\s\-]", "", job_name).strip()
        safe = re.sub(r"\s+", "-", safe)[:60]
        if safe:
            return f"{safe}_{ts}.csv"
    return f"waf_merged_{token}_{ts}.csv"


def _file_preview(df, fields):
    """Build the per-file payload for the UI mapping step."""
    cols = [str(c) for c in df.columns]
    sample_rows = []
    for _, row in df.head(3).iterrows():
        sample_rows.append({c: safe_str(row.get(c, "")) for c in cols})
    return {
        "uploaded":           True,
        "columns":            cols,
        "row_count":          len(df),
        "sample_rows":        sample_rows,
        "target_fields":      [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in fields],
        "suggested_mappings": _suggest_mapping(cols, fields),
    }


# ── Core merge ─────────────────────────────────────────────────────────────────

def merge_files(df_epic, df_feature, df_story, col_map, has_epic=True, has_feature=True):
    """Merge with explicit user-confirmed mappings.

    col_map structure:
      {"epic": {field_key: header}, "feature": {...}, "story": {...}}

    Returns (merged_rows, stats, issues_seed).
    Each merged row carries _status (one-of) and _is_complete (bool) used
    downstream for the analysis filter.
    """
    em = col_map.get("epic")    or {}
    fm = col_map.get("feature") or {}
    sm = col_map.get("story")   or {}

    # ── Build epic lookup keyed by lowercased Epic Name ───────────────────────
    epic_lookup = {}
    _epic_count_set = set()
    if df_epic is not None:
        for _, row in df_epic.iterrows():
            raw_name = safe_str(row.get(em.get("name_col"), "")) if em.get("name_col") else ""
            if not raw_name:
                continue
            clean_name, rc_from_name = extract_run_change_from_name(raw_name)
            waf_raw   = safe_str(row.get(em.get("waf_col"), "")) if em.get("waf_col") else ""
            waf_color, waf_category = parse_waf_field(waf_raw)
            rc_explicit = safe_str(row.get(em.get("run_change_col"), "")) if em.get("run_change_col") else ""
            entry = {
                "id":           safe_str(row.get(em.get("id_col"), ""))    if em.get("id_col")    else "",
                "name":         raw_name,
                "clean_name":   clean_name,
                "desc":         safe_str(row.get(em.get("desc_col"), ""))  if em.get("desc_col")  else "",
                "block":        safe_str(row.get(em.get("block_col"), "")) if em.get("block_col") else "",
                "waf":          waf_raw,
                "waf_color":    waf_color,
                "waf_category": waf_category,
                "run_change":   rc_explicit or rc_from_name,
            }
            epic_lookup[raw_name.lower()]   = entry
            if clean_name and clean_name.lower() != raw_name.lower():
                epic_lookup[clean_name.lower()] = entry
            _epic_count_set.add(clean_name.lower() if clean_name else raw_name.lower())

    # ── Build feature lookup keyed by lowercased Feature Name ─────────────────
    feature_lookup = {}
    if df_feature is not None:
        for _, row in df_feature.iterrows():
            name = safe_str(row.get(fm.get("name_col"), "")) if fm.get("name_col") else ""
            if not name:
                continue
            feature_lookup[name.lower()] = {
                "id":        safe_str(row.get(fm.get("id_col"), ""))        if fm.get("id_col")        else "",
                "name":      name,
                "desc":      safe_str(row.get(fm.get("desc_col"), ""))      if fm.get("desc_col")      else "",
                "tot":       safe_str(row.get(fm.get("tot_col"), ""))       if fm.get("tot_col")       else "",
                "pi":        safe_str(row.get(fm.get("pi_col"), ""))        if fm.get("pi_col")        else "",
                "epic_name": safe_str(row.get(fm.get("epic_name_col"), "")) if fm.get("epic_name_col") else "",
            }

    merged_rows        = []
    unmatched_features = 0
    unmatched_epics    = 0
    no_feature_ref     = 0
    missing_waf_count  = 0

    for _, row in df_story.iterrows():
        story_id      = safe_str(row.get(sm.get("id_col"), ""))            if sm.get("id_col")            else ""
        story_name    = safe_str(row.get(sm.get("name_col"), ""))          if sm.get("name_col")          else ""
        story_desc    = safe_str(row.get(sm.get("desc_col"), ""))          if sm.get("desc_col")          else ""
        story_pts     = safe_str(row.get(sm.get("points_col"), ""))        if sm.get("points_col")        else ""
        team          = safe_str(row.get(sm.get("team_col"), ""))          if sm.get("team_col")          else ""
        feat_name_ref = safe_str(row.get(sm.get("feature_name_col"), "")) if sm.get("feature_name_col") else ""

        # Look up feature by name (case-insensitive)
        feat_data  = feature_lookup.get(feat_name_ref.lower(), {}) if feat_name_ref else {}
        feat_found = bool(feat_data)
        if has_feature:
            if not feat_name_ref:
                no_feature_ref += 1
            elif not feat_found:
                unmatched_features += 1

        feat_id        = feat_data.get("id",   "")
        feat_name      = feat_data.get("name", feat_name_ref)
        feat_desc      = feat_data.get("desc", "")
        tot            = feat_data.get("tot",  "")
        pi_name        = feat_data.get("pi",   "")
        epic_name_ref  = feat_data.get("epic_name", "")

        # Look up epic by name (case-insensitive)
        epic_data  = epic_lookup.get(epic_name_ref.lower(), {}) if epic_name_ref else {}
        epic_found = bool(epic_data)
        if has_epic and has_feature and feat_found and epic_name_ref and not epic_found:
            unmatched_epics += 1

        epic_id       = epic_data.get("id",           "")
        epic_name     = epic_data.get("clean_name",   epic_data.get("name", epic_name_ref))
        epic_desc     = epic_data.get("desc",         "")
        block         = epic_data.get("block",        "")
        waf_raw       = epic_data.get("waf",          "")
        waf_color     = epic_data.get("waf_color",    "")
        waf_category  = epic_data.get("waf_category", "")
        run_change    = epic_data.get("run_change",   "")

        # ── Status & completeness flag ─────────────────────────────────────
        # Definition of "complete" adapts to which files were uploaded:
        #   - story-only          → complete iff story_name present
        #   - story + feature     → also requires feat_found
        #   - story + feature+epic→ also requires epic resolves (when feat has epic_name)
        if not story_name:
            status = "missing_feature"   # bucket — story unusable for analysis
        elif has_feature and not feat_found:
            status = "missing_feature"
        elif has_epic and has_feature and feat_found and epic_name_ref and not epic_found:
            status = "missing_epic"
        else:
            status = "complete"

        is_complete = (status == "complete")
        # missing_waf is an informational flag — does NOT block analysis
        flag_missing_waf = is_complete and has_epic and feat_found and epic_found and not waf_category
        if flag_missing_waf:
            missing_waf_count += 1

        merged_rows.append({
            # ── Output columns ──────────────────────────────────────────────
            "PI Name":        pi_name,
            "Epic Id":        epic_id,
            "Epic Name":      epic_name,
            "Epic Desc":      epic_desc,
            "Block":          block,
            "WAF":            waf_raw,
            "WAF Color":      waf_color,
            "WAF Category":   waf_category,
            "Run/Change":     run_change,
            "Feature Id":     feat_id,
            "Feature Name":   feat_name,
            "Feature Desc":   feat_desc,
            "Team of Teams":  tot,
            "Story Id":       story_id,
            "Story Name":     story_name,
            "Story Desc":     story_desc,
            "Story Points":   story_pts,
            "Assigned Teams": team,
            "Status":         "Complete" if is_complete else (
                                  "Missing Feature" if status == "missing_feature" else "Missing Epic"
                              ),
            # ── Validation metadata (stripped before CSV write) ─────────────
            "_status":          status,
            "_is_complete":     is_complete,
            "_flag_missing_waf": flag_missing_waf,
            "_story_id":        story_id,
            "_story_name":      story_name,
            "_feat_name_ref":   feat_name_ref,
            "_feat_found":      feat_found,
            "_epic_name_ref":   epic_name_ref,
            "_epic_found":      epic_found,
            "_waf_raw":         waf_raw,
        })

    # ── Aggregate stats ──────────────────────────────────────────────────────
    complete_count = sum(1 for r in merged_rows if r["_is_complete"])
    orphan_count   = len(merged_rows) - complete_count
    stats = {
        "epics":              len(_epic_count_set),
        "features":           len(feature_lookup),
        "stories":            len(df_story),
        "complete":           complete_count,
        "orphans":            orphan_count,
        "missing_feature":    sum(1 for r in merged_rows if r["_status"] == "missing_feature"),
        "missing_epic":       sum(1 for r in merged_rows if r["_status"] == "missing_epic"),
        "missing_waf":        missing_waf_count,
        "unmatched_features": unmatched_features,
        "unmatched_epics":    unmatched_epics,
        "no_feature_ref":     no_feature_ref,
    }

    return merged_rows, stats, epic_lookup, feature_lookup


def build_issues(merged_rows, epic_lookup, feature_lookup, has_feature=True, has_epic=True):
    """Inspect merged rows → structured issue lists for the UI."""
    orphan_stories  = []
    orphan_features = []
    missing_waf     = []
    unknown_color   = []

    if has_feature and has_epic:
        for feat_lower, feat in feature_lookup.items():
            epic_ref = feat.get("epic_name", "")
            if epic_ref and epic_ref.lower() not in epic_lookup:
                orphan_features.append({
                    "feature_id":   feat.get("id", ""),
                    "feature_name": feat.get("name", ""),
                    "missing_epic": epic_ref,
                })

    for row in merged_rows:
        sid   = row["_story_id"]
        title = row["_story_name"] or sid or "?"

        if has_feature:
            feat_ref   = row["_feat_name_ref"]
            feat_found = row["_feat_found"]
            if feat_ref and not feat_found:
                orphan_stories.append({
                    "story_id":        sid,
                    "story_title":     title,
                    "missing_feature": feat_ref,
                })
            elif not feat_ref:
                orphan_stories.append({
                    "story_id":        sid,
                    "story_title":     title,
                    "missing_feature": "(no Feature Name set)",
                })

        if row["_flag_missing_waf"]:
            missing_waf.append({"story_id": sid, "story_title": title})

        waf_raw = row["WAF"]
        color   = row["WAF Color"]
        if waf_raw and not color:
            unknown_color.append({
                "story_id":     sid,
                "story_title":  title,
                "waf_category": waf_raw,
            })

    total = (len(orphan_stories) + len(orphan_features) +
             len(missing_waf) + len(unknown_color))

    return {
        "orphan_stories":  orphan_stories,
        "orphan_features": orphan_features,
        "missing_waf":     missing_waf,
        "unknown_color":   unknown_color,
        "total":           total,
        "clean":           total == 0,
    }


# ── CSV serialization ─────────────────────────────────────────────────────────

def _public_row(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def rows_to_csv_bytes(rows, rejected_ids=None, only_complete=False, only_orphans=False):
    """Serialize output rows to CSV bytes.
    - rejected_ids: drop these story IDs (manual reject)
    - only_complete: keep only rows with _is_complete=True
    - only_orphans:  keep only rows with _is_complete=False
    """
    rejected = set(rejected_ids or [])
    keep = []
    for r in rows:
        sid = r.get("_story_id", r.get("Story Id", ""))
        if sid in rejected:
            continue
        if only_complete and not r.get("_is_complete"):
            continue
        if only_orphans and r.get("_is_complete"):
            continue
        keep.append(_public_row(r))
    df = pd.DataFrame(keep, columns=OUTPUT_COLUMNS)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@merge_bp.route("/api/merge/preview", methods=["POST"])
def merge_preview():
    """Phase 1: parse the uploaded files and return per-file mapping suggestions
    + sample rows. The DataFrames are cached server-side; the client confirms
    or adjusts mappings, then calls /api/merge/process with the token."""
    _gc_store()

    def _has_file(name):
        return name in request.files and request.files[name].filename != ""

    if not _has_file("story_file"):
        return jsonify({"error": "Story file is required."}), 400

    has_feature = _has_file("feature_file")
    has_epic    = _has_file("epic_file")

    try:
        df_story   = read_file(request.files["story_file"])
        df_feature = read_file(request.files["feature_file"]) if has_feature else None
        df_epic    = read_file(request.files["epic_file"])    if has_epic    else None
    except Exception as exc:
        return jsonify({"error": f"Failed to read uploaded files: {exc}"}), 400

    token = uuid.uuid4().hex   # full UUID — collision-safe
    _merge_store[token] = {
        "epic_df":     df_epic,
        "feature_df":  df_feature,
        "story_df":    df_story,
        "has_epic":    has_epic,
        "has_feature": has_feature,
        "created_at":  time.time(),
    }

    files_payload = {
        "story": _file_preview(df_story, STORY_FIELDS),
    }
    if has_feature:
        files_payload["feature"] = _file_preview(df_feature, FEATURE_FIELDS)
    else:
        files_payload["feature"] = {"uploaded": False}
    if has_epic:
        files_payload["epic"] = _file_preview(df_epic, EPIC_FIELDS)
    else:
        files_payload["epic"] = {"uploaded": False}

    # Required-fields list per file — adjusted for which files were uploaded.
    # Feature.epic_name_col is only required if Epic file is present.
    # Story.feature_name_col is only required if Feature file is present.
    required = {
        "story":   [f["key"] for f in STORY_FIELDS   if f["required"] and (has_feature or f["key"] != "feature_name_col")],
        "feature": [f["key"] for f in FEATURE_FIELDS if f["required"] and (has_epic    or f["key"] != "epic_name_col")] if has_feature else [],
        "epic":    [f["key"] for f in EPIC_FIELDS    if f["required"]] if has_epic    else [],
    }

    return jsonify({
        "token":    token,
        "files":    files_payload,
        "required": required,
    })


@merge_bp.route("/api/merge/process", methods=["POST"])
def merge_process():
    """Phase 2: run the merge with user-confirmed mappings. Returns stats,
    preview rows, issues, and a per-row status field used by the UI to
    paint orphan rows."""
    _gc_store()
    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    if not token or token not in _merge_store:
        return jsonify({"error": "Session expired or invalid token. Please re-upload files."}), 404

    state = _merge_store[token]
    df_epic    = state.get("epic_df")
    df_feature = state.get("feature_df")
    df_story   = state.get("story_df")
    has_epic    = state.get("has_epic", False)
    has_feature = state.get("has_feature", False)

    raw_mappings = body.get("mappings") or {}
    col_map = {
        "epic":    raw_mappings.get("epic")    or {},
        "feature": raw_mappings.get("feature") or {},
        "story":   raw_mappings.get("story")   or {},
    }

    # Validate required fields (only for files that were uploaded).
    errors = []
    def _check(file_key, fields, file_uploaded, requires_join_to=None):
        if not file_uploaded:
            return
        m = col_map.get(file_key) or {}
        for f in fields:
            if not f["required"]:
                continue
            # Conditional join-key requirements
            if f["key"] == "epic_name_col"   and not has_epic:    continue
            if f["key"] == "feature_name_col" and not has_feature: continue
            if not m.get(f["key"]):
                errors.append(f"{file_key.title()} file: '{f['label']}' must be mapped.")
    _check("story",   STORY_FIELDS,   True)
    _check("feature", FEATURE_FIELDS, has_feature)
    _check("epic",    EPIC_FIELDS,    has_epic)
    if errors:
        return jsonify({"error": "Required mappings missing.", "errors": errors}), 400

    try:
        merged_rows, stats, epic_lookup, feature_lookup = merge_files(
            df_epic, df_feature, df_story, col_map,
            has_epic=has_epic, has_feature=has_feature,
        )
    except Exception as exc:
        return jsonify({"error": f"Merge failed: {exc}"}), 500

    issues = build_issues(merged_rows, epic_lookup, feature_lookup,
                          has_feature=has_feature, has_epic=has_epic)
    issues["missing_files"] = (["epic"]    if not has_epic    else []) + \
                              (["feature"] if not has_feature else [])

    # Cache the merged rows on the same token for download/submit.
    state["merged_rows"] = merged_rows
    state["created_at"]  = time.time()

    def _preview_row(r):
        row = _public_row(r)
        row["_status"]      = r["_status"]
        row["_is_complete"] = r["_is_complete"]
        row["_flag_missing_waf"] = r["_flag_missing_waf"]
        return row

    # Sort preview so orphans float to the top — easier triage
    sorted_rows = sorted(
        merged_rows,
        key=lambda r: (0 if not r["_is_complete"] else 1, 0 if r["_flag_missing_waf"] else 1)
    )

    return jsonify({
        "token":      token,
        "stats":      stats,
        "issues":     issues,
        "preview":    [_preview_row(r) for r in sorted_rows[:50]],
        "columns":    OUTPUT_COLUMNS,
        "column_map": col_map,
    })


@merge_bp.route("/api/merge/download/<token>", methods=["POST"])
def merge_download(token):
    """Return merged CSV (everything, with Status column) excluding manual rejections."""
    _gc_store()
    if not re.fullmatch(r"[0-9a-f]{8,}", token):
        return jsonify({"error": "Invalid token"}), 400

    state = _merge_store.get(token)
    if not state or "merged_rows" not in state:
        return jsonify({"error": "Session expired — please re-process files"}), 404

    body         = request.get_json(silent=True) or {}
    rejected_ids = body.get("rejected_ids", [])
    job_name     = str(body.get("job_name", "")).strip()
    only_complete = bool(body.get("only_complete", False))
    only_orphans  = bool(body.get("only_orphans",  False))

    suffix = ""
    if only_complete: suffix = "_complete"
    elif only_orphans: suffix = "_orphans"
    filename = make_filename(job_name + suffix if job_name else "", token)

    csv_bytes = rows_to_csv_bytes(
        state["merged_rows"],
        rejected_ids=rejected_ids,
        only_complete=only_complete,
        only_orphans=only_orphans,
    )
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@merge_bp.route("/api/merge/send-to-classifier/<token>", methods=["POST"])
def merge_send_to_classifier(token):
    """Filter to ONLY complete rows (orphans excluded), write final CSV to
    uploads folder, return mapping payload so the frontend can hand off to
    the bulk-verify pipeline. Manual rejections are also honored."""
    _gc_store()
    if not re.fullmatch(r"[0-9a-f]{8,}", token):
        return jsonify({"error": "Invalid token"}), 400

    state = _merge_store.get(token)
    if not state or "merged_rows" not in state:
        return jsonify({"error": "Session expired — please re-process files"}), 404

    from config import UPLOAD_FOLDER
    from state import _preview_store

    rejected_ids = json.loads(request.form.get("rejected_ids", "[]"))
    job_name     = request.form.get("job_name", "").strip()
    dest_name    = make_filename(job_name, token)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    dest_path = os.path.join(UPLOAD_FOLDER, dest_name)

    # ALWAYS only_complete=True for analysis — orphans don't go to AI
    csv_bytes = rows_to_csv_bytes(state["merged_rows"], rejected_ids=rejected_ids, only_complete=True)
    with open(dest_path, "wb") as f:
        f.write(csv_bytes)

    df = pd.read_csv(dest_path)
    original_columns = list(df.columns)
    df.columns = [c.strip().lower() for c in df.columns]

    def _find(keywords, exclude=None):
        exclude = exclude or set()
        for kw in keywords:
            for col in df.columns:
                if kw in col and col not in exclude:
                    return col
        return None

    target_fields = [
        {"key": "title",          "label": "Story Title",        "required": True,  "keywords": ["story name", "story title", "title"]},
        {"key": "description",    "label": "Story Description",  "required": False, "keywords": ["story desc", "story description", "description"]},
        {"key": "epic_id",        "label": "Epic ID",            "required": False, "keywords": ["epic id", "epic_id"]},
        {"key": "epic",           "label": "Epic Name",          "required": False, "keywords": ["epic name"]},
        {"key": "feature_id",     "label": "Feature ID",         "required": False, "keywords": ["feature id", "feature_id"]},
        {"key": "parent_feature", "label": "Feature Name",       "required": False, "keywords": ["feature name"]},
        {"key": "story_id",       "label": "Story ID",           "required": False, "keywords": ["story id", "story_id"]},
        {"key": "story_points",   "label": "Story Points",       "required": False, "keywords": ["story points", "story_points"]},
        {"key": "waf_category",   "label": "WAF Category",       "required": False, "keywords": ["waf category", "waf_category"]},
        {"key": "waf_color",      "label": "WAF Color",          "required": False, "keywords": ["waf color", "waf_color"]},
        {"key": "team_of_teams",  "label": "Team of Teams",      "required": False, "keywords": ["team of teams", "team_of_teams"]},
        {"key": "run_change",     "label": "Run / Change",       "required": False, "keywords": ["run/change", "run or change", "run_change", "run change"]},
        {"key": "confidence",     "label": "Confidence",         "required": False, "keywords": ["confidence", "conf"]},
        {"key": "team",           "label": "Assigned Teams",     "required": False, "keywords": ["assigned teams", "assigned team", "team"]},
        {"key": "pi_number",      "label": "PI Name",            "required": False, "keywords": ["pi name", "pi number"]},
        {"key": "timestamp",      "label": "Timestamp",          "required": False, "keywords": ["timestamp", "time stamp", "date"]},
    ]

    claimed_cols = set()
    suggested    = {}
    for f in target_fields:
        matched = _find(f["keywords"], exclude=claimed_cols)
        suggested[f["key"]] = matched or ""
        if matched:
            claimed_cols.add(matched)

    sample_rows = [{col: str(row.get(col, "")) for col in df.columns}
                   for _, row in df.head(3).iterrows()]
    preview_id  = str(uuid.uuid4())
    _preview_store[preview_id] = {
        "df": df, "filename": dest_name, "ext": "csv",
        "filepath": dest_path, "created": time.time(),
    }

    return jsonify({
        "success":            True,
        "filename":           dest_name,
        "file_columns":       list(df.columns),
        "original_columns":   original_columns,
        "suggested_mappings": suggested,
        "target_fields":      [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in target_fields],
        "sample_rows":        sample_rows,
        "total_rows":         len(df),
        "preview_id":         preview_id,
    })
