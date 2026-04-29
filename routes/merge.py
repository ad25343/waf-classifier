"""
WAF Classifier — File Merger Blueprint
Merges 3 JIRA export files (Epic, Feature, Story) into the canonical WAF import format.

Join rules:
  Epic ↔ Feature  — joined by Epic Name
  Feature ↔ Story — joined by Feature Name

WAF field on the Epic file is in the format "ORANGE - Enterprise Strategic Priority".
It is split on " - " to derive WAF Color (left) and WAF Category (right).
"""

import io
import os
import re
import tempfile
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

# In-memory store: token -> full merged rows (for reject/refilter on submit)
_merge_store = {}

# ── Known WAF colors ───────────────────────────────────────────────────────────
KNOWN_COLORS = {"GRAY", "BLACK", "RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE", "TEAL"}

# ── Column keyword definitions ─────────────────────────────────────────────────
EPIC_KEYWORDS = {
    "id_col":         ["epic id", "jira saas epic", "epic#", "epic key", "epic number"],
    "name_col":       ["epic name", "epic summary", "epic title", "summary"],
    "desc_col":       ["epic description", "epic desc"],
    "block_col":      ["block", "program/org", "program org", "org block"],
    "waf_col":        ["work alignment framework", "work alignment", "waf"],
    "run_change_col": ["run/change", "run or change", "run change", "run_change"],
}

FEATURE_KEYWORDS = {
    "epic_name_col": ["epic name"],          # join key — must match Epic Name in epic file
    "id_col":        ["feature id", "jira saas feature", "feature key"],
    "name_col":      ["feature name", "feature summary", "summary"],
    "desc_col":      ["feature description", "feature desc"],
    "tot_col":       ["team of teams", "team_of_teams"],
    "pi_col":        ["pi name", "pi number", " pi "],
}

STORY_KEYWORDS = {
    "feature_name_col": ["feature name"],    # join key — must match Feature Name in feature file
    "id_col":           ["story id", "story#", "story number", "issue key", "key"],
    "name_col":         ["story name", "summary", "title", "name"],
    "desc_col":         ["story desc", "story description", "description"],
    "points_col":       ["story points", "story_points", "points", "sp", "estimate"],
    "team_col":         ["assigned teams", "assigned team", "assigned_team", "teams", "team"],
}

OUTPUT_COLUMNS = [
    "PI Name",
    "Epic Id", "Epic Name", "Epic Desc", "Block",
    "WAF", "WAF Color", "WAF Category", "Run/Change",
    "Feature Id", "Feature Name", "Feature Desc", "Team of Teams",
    "Story Id", "Story Name", "Story Desc", "Story Points", "Assigned Teams",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_col(headers, keywords):
    h_map = {h.lower().strip(): h for h in headers}
    for kw in keywords:
        for h_lower, h_orig in h_map.items():
            if kw in h_lower:
                return h_orig
    return None


_RUN_CHANGE_SUFFIX = re.compile(r'\s*\((run|change)\)\s*$', re.IGNORECASE)

def extract_run_change_from_name(name):
    """
    Strip a trailing '(Run)' or '(Change)' from an epic name.
    Returns (clean_name, run_change_value).
    e.g. 'Payments Modernization (Change)' -> ('Payments Modernization', 'Change')
    e.g. 'Identity Mgmt'                   -> ('Identity Mgmt', '')
    """
    m = _RUN_CHANGE_SUFFIX.search(name)
    if m:
        clean = _RUN_CHANGE_SUFFIX.sub("", name).strip()
        return clean, m.group(1).capitalize()   # 'Run' or 'Change'
    return name, ""


def parse_waf_field(waf_value):
    """
    Parse a WAF field like 'ORANGE - Enterprise Strategic Priority'.
    Returns (waf_color, waf_category).
    The color is the first segment (before ' - ') when it matches a known color.
    Falls back to normalize_waf_category for unrecognized formats.
    """
    if not waf_value or (isinstance(waf_value, float) and pd.isna(waf_value)):
        return "", ""
    val = str(waf_value).strip()
    if " - " in val:
        parts = val.split(" - ", 1)
        color_candidate = parts[0].strip().upper()
        category_part   = parts[1].strip()
        if color_candidate in KNOWN_COLORS:
            return color_candidate, category_part
        # Color segment not recognized — normalize the category part
        normalized = _normalize_waf(category_part)[0] if category_part else ""
        return "", normalized or category_part
    # No separator — try to normalize entire value as category
    normalized = _normalize_waf(val)[0] if val else ""
    return "", normalized or val


def read_file(file_storage):
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[-1].lower()
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


def detect_column_map(df_epic, df_feature, df_story):
    return {
        "epic":    {k: find_col(list(df_epic.columns),    v) for k, v in EPIC_KEYWORDS.items()}    if df_epic    is not None else None,
        "feature": {k: find_col(list(df_feature.columns), v) for k, v in FEATURE_KEYWORDS.items()} if df_feature is not None else None,
        "story":   {k: find_col(list(df_story.columns),   v) for k, v in STORY_KEYWORDS.items()},
    }


def make_filename(job_name, token):
    """Build a sanitized, timestamped filename."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    if job_name:
        safe = re.sub(r"[^\w\s\-]", "", job_name).strip()
        safe = re.sub(r"\s+", "-", safe)[:60]
        if safe:
            return f"{safe}_{ts}.csv"
    return f"waf_merged_{token}_{ts}.csv"


# ── Core merge + validation ───────────────────────────────────────────────────

def merge_files(df_epic, df_feature, df_story, col_map, has_epic=True, has_feature=True):
    """
    Merge DataFrames. df_epic and df_feature may be None (optional files).

    Join strategy (name-based, case-insensitive):
      - Epic lookup   keyed by Epic Name
      - Feature lookup keyed by Feature Name
      - Story rows look up Feature by Feature Name column;
        Feature rows carry the Epic Name which is used to look up the Epic.

    WAF is parsed from the Epic-level 'waf_col' field only.
    Returns (merged_rows, stats, epic_lookup, feature_lookup).
    Each merged row carries private _meta fields used for validation.
    """
    em = col_map["epic"]    or {}
    fm = col_map["feature"] or {}
    sm = col_map["story"]

    # ── Build epic lookup keyed by lowercased Epic Name ───────────────────────
    # Indexed by BOTH the raw name and the clean name (suffix stripped) so that
    # Feature files referencing either form resolve correctly.
    # e.g. "Payments Modernization (Change)" indexes under:
    #   "payments modernization (change)"  ← full form
    #   "payments modernization"           ← clean form (no suffix)
    epic_lookup   = {}   # lower_epic_name -> {id, name, desc, block, waf, waf_color, waf_category, run_change}
    _epic_count_set = set()   # unique clean names — used for accurate count in stats
    if df_epic is not None:
        for _, row in df_epic.iterrows():
            raw_name = safe_str(row.get(em["name_col"], "")) if em.get("name_col") else ""
            if not raw_name:
                continue
            # Extract (Run)/(Change) suffix from name as fallback for run_change
            clean_name, rc_from_name = extract_run_change_from_name(raw_name)
            waf_raw   = safe_str(row.get(em["waf_col"],  "")) if em.get("waf_col")  else ""
            waf_color, waf_category = parse_waf_field(waf_raw)
            # Explicit column wins over name-derived value
            rc_explicit = safe_str(row.get(em["run_change_col"], "")) if em.get("run_change_col") else ""
            entry = {
                "id":           safe_str(row.get(em["id_col"],    "")) if em.get("id_col")   else "",
                "name":         raw_name,          # preserve original name in output
                "clean_name":   clean_name,        # name without suffix
                "desc":         safe_str(row.get(em["desc_col"],  "")) if em.get("desc_col") else "",
                "block":        safe_str(row.get(em["block_col"], "")) if em.get("block_col") else "",
                "waf":          waf_raw,
                "waf_color":    waf_color,
                "waf_category": waf_category,
                "run_change":   rc_explicit or rc_from_name,
            }
            epic_lookup[raw_name.lower()]   = entry   # full name key
            epic_lookup[clean_name.lower()] = entry   # clean name key (no-op if no suffix)
            _epic_count_set.add(clean_name.lower())

    # ── Build feature lookup keyed by lowercased Feature Name ─────────────────
    feature_lookup = {}  # lower_feature_name -> {id, name, desc, tot, pi, epic_name}
    if df_feature is not None:
        for _, row in df_feature.iterrows():
            name = safe_str(row.get(fm["name_col"], "")) if fm.get("name_col") else ""
            if not name:
                continue
            feature_lookup[name.lower()] = {
                "id":        safe_str(row.get(fm["id_col"],        "")) if fm.get("id_col")        else "",
                "name":      name,
                "desc":      safe_str(row.get(fm["desc_col"],      "")) if fm.get("desc_col")      else "",
                "tot":       safe_str(row.get(fm["tot_col"],       "")) if fm.get("tot_col")       else "",
                "pi":        safe_str(row.get(fm["pi_col"],        "")) if fm.get("pi_col")        else "",
                "epic_name": safe_str(row.get(fm["epic_name_col"], "")) if fm.get("epic_name_col") else "",
            }

    merged_rows        = []
    unmatched_features = 0
    unmatched_epics    = 0

    for _, row in df_story.iterrows():
        story_id       = safe_str(row.get(sm["id_col"],           "")) if sm.get("id_col")           else ""
        story_name     = safe_str(row.get(sm["name_col"],         "")) if sm.get("name_col")         else ""
        story_desc     = safe_str(row.get(sm["desc_col"],         "")) if sm.get("desc_col")         else ""
        story_pts      = safe_str(row.get(sm["points_col"],       "")) if sm.get("points_col")       else ""
        team           = safe_str(row.get(sm["team_col"],         "")) if sm.get("team_col")         else ""
        feat_name_ref  = safe_str(row.get(sm["feature_name_col"], "")) if sm.get("feature_name_col") else ""

        # Look up feature by name (case-insensitive)
        feat_data  = feature_lookup.get(feat_name_ref.lower(), {}) if feat_name_ref else {}
        feat_found = bool(feat_data)
        if has_feature and feat_name_ref and not feat_found:
            unmatched_features += 1

        feat_id        = feat_data.get("id",   "")
        feat_name      = feat_data.get("name", feat_name_ref)   # preserve ref if no lookup
        feat_desc      = feat_data.get("desc", "")
        tot            = feat_data.get("tot",  "")
        pi_name        = feat_data.get("pi",   "")
        epic_name_ref  = feat_data.get("epic_name", "")

        # Look up epic by name (case-insensitive)
        epic_data  = epic_lookup.get(epic_name_ref.lower(), {}) if epic_name_ref else {}
        epic_found = bool(epic_data)
        if has_epic and has_feature and epic_name_ref and not epic_found:
            unmatched_epics += 1

        epic_id       = epic_data.get("id",           "")
        epic_name     = epic_data.get("clean_name",   epic_data.get("name", epic_name_ref))
        epic_desc     = epic_data.get("desc",         "")
        block         = epic_data.get("block",        "")
        waf_raw       = epic_data.get("waf",          "")
        waf_color     = epic_data.get("waf_color",    "")
        waf_category  = epic_data.get("waf_category", "")
        run_change    = epic_data.get("run_change",   "")

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
            # ── Validation metadata (stripped before CSV write) ─────────────
            "_story_id":       story_id,
            "_story_name":     story_name,
            "_feat_name_ref":  feat_name_ref,
            "_feat_found":     feat_found,
            "_epic_name_ref":  epic_name_ref,
            "_epic_found":     epic_found,
            "_waf_raw":        waf_raw,
        })

    stats = {
        "epics":              len(_epic_count_set) or len(epic_lookup),
        "features":           len(feature_lookup),
        "stories":            len(df_story),
        "matched":            sum(1 for r in merged_rows if r["_feat_found"]),
        "unmatched_features": unmatched_features,
        "unmatched_epics":    unmatched_epics,
    }

    return merged_rows, stats, epic_lookup, feature_lookup


def build_issues(merged_rows, epic_lookup, feature_lookup, has_feature=True, has_epic=True):
    """
    Inspect merged rows and return structured issue lists.
    has_feature / has_epic control whether orphan checks apply.
    """
    orphan_stories  = []
    orphan_features = []
    missing_waf     = []
    unknown_color   = []

    # Orphan features: features whose Epic Name doesn't resolve to a known epic
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

        # Orphan stories: feature name reference didn't resolve
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

        # Missing WAF category
        if not row["WAF Category"]:
            missing_waf.append({"story_id": sid, "story_title": title})

        # WAF field present but color couldn't be parsed
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


def rows_to_csv_bytes(rows, rejected_ids=None):
    """Serialize output rows to CSV bytes, excluding rejected story IDs."""
    rejected = set(rejected_ids or [])
    clean = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in rows
        if r.get("_story_id", r.get("Story Id", "")) not in rejected
    ]
    df = pd.DataFrame(clean, columns=OUTPUT_COLUMNS)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@merge_bp.route("/api/merge/process", methods=["POST"])
def merge_process():
    # Story file is required; Feature and Epic are optional
    def _has_file(name):
        return name in request.files and request.files[name].filename != ""

    if not _has_file("story_file"):
        return jsonify({"error": "Story file is required to run the merge."}), 400

    has_feature  = _has_file("feature_file")
    has_epic     = _has_file("epic_file")
    missing_files = (["epic"] if not has_epic else []) + (["feature"] if not has_feature else [])

    try:
        df_story   = read_file(request.files["story_file"])
        df_feature = read_file(request.files["feature_file"]) if has_feature else None
        df_epic    = read_file(request.files["epic_file"])    if has_epic    else None
    except Exception as exc:
        return jsonify({"error": f"Failed to read uploaded files: {exc}"}), 400

    col_map = detect_column_map(df_epic, df_feature, df_story)

    try:
        merged_rows, stats, epic_lookup, feature_lookup = merge_files(
            df_epic, df_feature, df_story, col_map,
            has_epic=has_epic, has_feature=has_feature,
        )
    except Exception as exc:
        return jsonify({"error": f"Merge failed: {exc}"}), 500

    issues = build_issues(merged_rows, epic_lookup, feature_lookup,
                          has_feature=has_feature, has_epic=has_epic)
    issues["missing_files"] = missing_files

    # Store full rows for reject filtering on submit/download
    token    = uuid.uuid4().hex[:8]
    _merge_store[token] = merged_rows

    # Write initial temp CSV (no rejections yet)
    tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
    csv_bytes = rows_to_csv_bytes(merged_rows)
    with open(tmp_path, "wb") as f:
        f.write(csv_bytes)

    def _preview_row(r):
        row = {k: v for k, v in r.items() if not k.startswith("_")}
        row["_diff_missing_waf"] = not row.get("WAF Category", "")
        return row

    return jsonify({
        "token":      token,
        "stats":      stats,
        "issues":     issues,
        "preview":    [_preview_row(r) for r in merged_rows[:50]],
        "columns":    OUTPUT_COLUMNS,
        "column_map": col_map,
    })


@merge_bp.route("/api/merge/download/<token>", methods=["POST"])
def merge_download(token):
    """Return merged CSV, excluding any rejected story IDs."""
    if not re.fullmatch(r"[0-9a-f]{8}", token):
        return jsonify({"error": "Invalid token"}), 400

    rows = _merge_store.get(token)
    if rows is None:
        tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
        if not os.path.exists(tmp_path):
            return jsonify({"error": "Session expired — please re-process files"}), 404
        return send_file(tmp_path, mimetype="text/csv", as_attachment=True,
                         download_name=f"waf_merged_{token}.csv")

    body         = request.get_json(silent=True) or {}
    rejected_ids = body.get("rejected_ids", [])
    job_name     = str(body.get("job_name", "")).strip()
    filename     = make_filename(job_name, token)

    csv_bytes = rows_to_csv_bytes(rows, rejected_ids)
    return send_file(
        io.BytesIO(csv_bytes),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@merge_bp.route("/api/merge/send-to-classifier/<token>", methods=["POST"])
def merge_send_to_classifier(token):
    """
    Filter out rejected rows, write final CSV to uploads folder, run
    bulk-verify preview logic, return full preview JSON.
    Frontend stores in sessionStorage → /history auto-triggers mapping step.
    """
    if not re.fullmatch(r"[0-9a-f]{8}", token):
        return jsonify({"error": "Invalid token"}), 400

    rows = _merge_store.get(token)
    if rows is None:
        tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
        if not os.path.exists(tmp_path):
            return jsonify({"error": "Session expired — please re-process files"}), 404

    import json, shutil, time as _time
    from config import UPLOAD_FOLDER
    from state import _preview_store

    rejected_ids = json.loads(request.form.get("rejected_ids", "[]"))
    job_name     = request.form.get("job_name", "").strip()
    dest_name    = make_filename(job_name, token)

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    dest_path = os.path.join(UPLOAD_FOLDER, dest_name)

    if rows is not None:
        csv_bytes = rows_to_csv_bytes(rows, rejected_ids)
        with open(dest_path, "wb") as f:
            f.write(csv_bytes)
    else:
        tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
        shutil.copy2(tmp_path, dest_path)

    # Run column-detection (same as /api/bulk-verify/preview)
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
        # ── Required story content ─────────────────────────────────────────────
        {"key": "title",          "label": "Story Title",        "required": True,  "keywords": ["story name", "story title", "title"]},
        {"key": "description",    "label": "Story Description",  "required": False, "keywords": ["story desc", "story description", "description"]},
        # ── Hierarchy: Epic → Feature → Story ─────────────────────────────────
        {"key": "epic_id",        "label": "Epic ID",            "required": False, "keywords": ["epic id", "epic_id"]},
        {"key": "epic",           "label": "Epic Name",          "required": False, "keywords": ["epic name"]},
        {"key": "feature_id",     "label": "Feature ID",         "required": False, "keywords": ["feature id", "feature_id"]},
        {"key": "parent_feature", "label": "Feature Name",       "required": False, "keywords": ["feature name"]},
        {"key": "story_id",       "label": "Story ID",           "required": False, "keywords": ["story id", "story_id"]},
        {"key": "story_points",   "label": "Story Points",       "required": False, "keywords": ["story points", "story_points"]},
        # ── WAF Classification ─────────────────────────────────────────────────
        {"key": "waf_category",   "label": "WAF Category",       "required": False, "keywords": ["waf category", "waf_category"]},
        {"key": "waf_color",      "label": "WAF Color",          "required": False, "keywords": ["waf color", "waf_color"]},
        {"key": "team_of_teams",  "label": "Team of Teams",      "required": False, "keywords": ["team of teams", "team_of_teams"]},
        {"key": "run_change",     "label": "Run / Change",       "required": False, "keywords": ["run/change", "run or change", "run_change", "run change"]},
        {"key": "confidence",     "label": "Confidence",         "required": False, "keywords": ["confidence", "conf"]},
        # ── Organisation ───────────────────────────────────────────────────────
        {"key": "team",           "label": "Assigned Teams",     "required": False, "keywords": ["assigned teams", "assigned team", "team"]},
        {"key": "pi_number",      "label": "PI Name",            "required": False, "keywords": ["pi name", "pi number", " pi "]},
        {"key": "timestamp",      "label": "Timestamp",          "required": False, "keywords": ["timestamp", "time stamp", "date"]},
    ]

    claimed_cols = set()
    suggested    = {}
    for f in target_fields:
        matched = _find(f["keywords"], exclude=claimed_cols)
        suggested[f["key"]] = matched or ""
        if matched:
            claimed_cols.add(matched)

    sample_rows  = [{col: str(row.get(col, "")) for col in df.columns}
                    for _, row in df.head(3).iterrows()]
    preview_id   = str(uuid.uuid4())
    _preview_store[preview_id] = {
        "df": df, "filename": dest_name, "ext": "csv",
        "filepath": dest_path, "created": _time.time(),
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
