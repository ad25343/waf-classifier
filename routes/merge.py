"""
WAF Classifier — File Merger Blueprint
Merges 3 JIRA export files (Epic, Feature, Story) into the canonical WAF import format.
Includes data-quality validation before submit: orphans, WAF gaps, color gaps, divergence.
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

# ── WAF Color map ─────────────────────────────────────────────────────────────
WAF_COLOR_MAP = {
    "ktlo": "GRAY",
    "keep the lights": "GRAY",
    "business maintenance": "BLACK",
    "technical maintenance": "BLACK",
    "regulatory (operational)": "RED",
    "regulatory mandated": "RED",
    "enterprise strategic": "ORANGE",
    "top divisional": "YELLOW",
    "other block": "GREEN",
    "revenue": "GREEN",
    "efficiency": "BLUE",
    "operational": "BLUE",
    "new capability": "ORANGE",
    "tech debt": "YELLOW",
    "technical debt": "YELLOW",
    "security": "PURPLE",
}

KNOWN_COLORS = {"GRAY", "BLACK", "RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE", "TEAL"}

# ── Column keyword definitions ─────────────────────────────────────────────────
EPIC_KEYWORDS = {
    "id_col":   ["jira saas epic#", "epic#", "epic key", "epic id", "epic number"],
    "name_col": ["summary", "epic summary", "epic name", "epic title"],
    "waf_col":  ["work alignment framework", "work alignment", "waf"],
}

FEATURE_KEYWORDS = {
    "id_col":   ["jira saas feature key", "feature key", "feature id"],
    "name_col": ["feature summary", "feature name", "summary"],
    "epic_col": ["parent epic number", "parent epic", "epic number", "epic#"],
    "team_col": ["team of teams", "team"],
    "waf_col":  ["work alignment", "waf derived", "work category", "waf"],
}

STORY_KEYWORDS = {
    "id_col":        ["story #", "story#", "story number", "issue key", "key"],
    "title_col":     ["story name", "summary", "title", "name"],
    "feature_col":   ["parent feature", "feature key", "feature#", "feature"],
    "team_col":      ["teams", "team"],
    "waf_col":       ["waf derived", "work alignment", "waf"],
    "timestamp_col": ["resolved date", "created", "date", "timestamp"],
    "status_col":    ["status"],
}

OUTPUT_COLUMNS = [
    "Epic ID", "Feature ID", "Story ID",
    "Epic", "Parent Feature", "Story Title", "Story Description",
    "Team", "WAF Category", "WAF Color",
    "Sub-Category", "Confidence", "Run/Change",
    "Timestamp", "Issue Key",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_col(headers, keywords):
    h_map = {h.lower().strip(): h for h in headers}
    for kw in keywords:
        for h_lower, h_orig in h_map.items():
            if kw in h_lower:
                return h_orig
    return None


def resolve_waf_color(waf_value):
    if not waf_value or pd.isna(waf_value):
        return ""
    val = str(waf_value).lower().strip()
    for key, color in WAF_COLOR_MAP.items():
        if key in val:
            return color
    return ""


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
        "epic":    {k: find_col(list(df_epic.columns),    v) for k, v in EPIC_KEYWORDS.items()} if df_epic    is not None else None,
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
    Returns (merged_rows, stats, epic_lookup, feature_lookup).
    Each merged row carries private _meta fields used for validation.
    """
    em = col_map["epic"]    or {}
    fm = col_map["feature"] or {}
    sm = col_map["story"]

    # Build epic lookup (only when epic file provided)
    epic_lookup = {}
    if df_epic is not None and em.get("id_col"):
        for _, row in df_epic.iterrows():
            eid = safe_str(row.get(em["id_col"], ""))
            if eid:
                epic_lookup[eid] = {
                    "name": safe_str(row.get(em["name_col"], "")) if em.get("name_col") else "",
                    "waf":  safe_str(row.get(em["waf_col"],  "")) if em.get("waf_col")  else "",
                }

    # Build feature lookup (only when feature file provided)
    feature_lookup = {}
    if df_feature is not None and fm.get("id_col"):
        for _, row in df_feature.iterrows():
            fid = safe_str(row.get(fm["id_col"], ""))
            if fid:
                feature_lookup[fid] = {
                    "name":           safe_str(row.get(fm["name_col"],  "")) if fm.get("name_col")  else "",
                    "parent_epic_id": safe_str(row.get(fm["epic_col"],  "")) if fm.get("epic_col")  else "",
                    "team":           safe_str(row.get(fm["team_col"],  "")) if fm.get("team_col")  else "",
                    "waf":            safe_str(row.get(fm["waf_col"],   "")) if fm.get("waf_col")   else "",
                }

    merged_rows = []
    unmatched_features = 0
    unmatched_epics = 0

    for idx, row in df_story.iterrows():
        story_id  = safe_str(row.get(sm["id_col"],       "")) if sm["id_col"]       else ""
        title     = safe_str(row.get(sm["title_col"],    "")) if sm["title_col"]    else ""
        feat_ref  = safe_str(row.get(sm["feature_col"],  "")) if sm["feature_col"]  else ""
        s_team    = safe_str(row.get(sm["team_col"],     "")) if sm["team_col"]     else ""
        s_waf     = safe_str(row.get(sm["waf_col"],      "")) if sm["waf_col"]      else ""
        timestamp = safe_str(row.get(sm["timestamp_col"],"")) if sm["timestamp_col"] else ""

        feat_data    = feature_lookup.get(feat_ref, {})
        feat_found   = bool(feat_data)
        feat_name    = feat_data.get("name", "")
        f_team       = feat_data.get("team", "")
        f_waf        = feat_data.get("waf",  "")
        epic_ref     = feat_data.get("parent_epic_id", "")

        if has_feature and feat_ref and not feat_found:
            unmatched_features += 1

        epic_data  = epic_lookup.get(epic_ref, {})
        epic_found = bool(epic_data)
        epic_name  = epic_data.get("name", "")
        e_waf      = epic_data.get("waf",  "")

        if has_epic and epic_ref and not epic_found:
            unmatched_epics += 1

        raw_waf      = s_waf or f_waf or e_waf
        waf_category = _normalize_waf(raw_waf)[0] if raw_waf else ""
        team         = s_team or f_team
        waf_color    = resolve_waf_color(waf_category)

        merged_rows.append({
            # ── Output columns ──────────────────────────────────────────
            "Epic ID":           epic_ref,
            "Feature ID":        feat_ref,
            "Story ID":          story_id,
            "Epic":              epic_name,
            "Parent Feature":    feat_name,
            "Story Title":       title,
            "Story Description": "",
            "Team":              team,
            "WAF Category":      waf_category,
            "WAF Color":         waf_color,
            "Sub-Category":      "",
            "Confidence":        "",
            "Run/Change":        "",
            "Timestamp":         timestamp,
            "Issue Key":         story_id,
            # ── Validation metadata (stripped before CSV write) ─────────
            "_story_id":    story_id,
            "_feat_ref":    feat_ref,
            "_feat_found":  feat_found,
            "_epic_ref":    epic_ref,
            "_epic_found":  epic_found,
            "_s_waf":       s_waf,
            "_f_waf":       f_waf,
            "_e_waf":       e_waf,
        })

    stats = {
        "epics":              len(epic_lookup),
        "features":           len(feature_lookup),
        "stories":            len(df_story),
        "matched":            len(merged_rows) - unmatched_features,
        "unmatched_features": unmatched_features,
        "unmatched_epics":    unmatched_epics,
    }

    return merged_rows, stats, epic_lookup, feature_lookup


def build_issues(merged_rows, epic_lookup, feature_lookup, has_feature=True, has_epic=True):
    """
    Inspect merged rows and return structured issue lists.
    has_feature / has_epic control whether orphan checks apply
    (skipped when the relevant file was not uploaded).
    """
    orphan_stories   = []
    orphan_features  = []
    missing_waf      = []
    unknown_color    = []
    waf_divergence   = []

    # Orphan features only meaningful when both feature + epic files provided
    if has_feature and has_epic:
        for fid, feat in feature_lookup.items():
            parent_epic = feat.get("parent_epic_id", "")
            if parent_epic and parent_epic not in epic_lookup:
                orphan_features.append({
                    "feature_id":   fid,
                    "feature_name": feat.get("name", ""),
                    "missing_epic": parent_epic,
                })

    for row in merged_rows:
        sid   = row["_story_id"]
        title = row["Story Title"]

        # Orphan stories only meaningful when feature file was provided
        if has_feature:
            feat_ref   = row["_feat_ref"]
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
                    "missing_feature": "(no Parent Feature set)",
                })

        # Missing WAF
        waf = row["WAF Category"]
        if not waf:
            missing_waf.append({"story_id": sid, "story_title": title})

        # Unknown color
        color = row["WAF Color"]
        if waf and not color:
            unknown_color.append({
                "story_id":    sid,
                "story_title": title,
                "waf_category": waf,
            })

        # WAF divergence: story's own WAF tag vs its parent feature's WAF tag
        s_waf = row["_s_waf"]
        f_waf = row["_f_waf"]
        if s_waf and f_waf and s_waf.lower() != f_waf.lower():
            waf_divergence.append({
                "story_id":    sid,
                "story_title": title,
                "story_waf":   s_waf,
                "feature_waf": f_waf,
                "feature_id":  row["Feature ID"],
            })

    total = (len(orphan_stories) + len(orphan_features) +
             len(missing_waf) + len(unknown_color) + len(waf_divergence))

    return {
        "orphan_stories":  orphan_stories,
        "orphan_features": orphan_features,
        "missing_waf":     missing_waf,
        "unknown_color":   unknown_color,
        "waf_divergence":  waf_divergence,
        "total":           total,
        "clean":           total == 0,
    }


def rows_to_csv_bytes(rows, rejected_ids=None):
    """Serialize output rows to CSV bytes, excluding rejected story IDs."""
    rejected = set(rejected_ids or [])
    clean = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in rows
        if r.get("_story_id", r.get("Story ID", "")) not in rejected
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

    has_feature = _has_file("feature_file")
    has_epic    = _has_file("epic_file")
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
            has_epic=has_epic, has_feature=has_feature
        )
    except Exception as exc:
        return jsonify({"error": f"Merge failed: {exc}"}), 500

    issues = build_issues(merged_rows, epic_lookup, feature_lookup,
                          has_feature=has_feature, has_epic=has_epic)
    issues["missing_files"] = missing_files

    # Store full rows (including _meta) for reject filtering on submit/download
    token = uuid.uuid4().hex[:8]
    _merge_store[token] = merged_rows

    # Write initial temp CSV (no rejections yet)
    tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
    csv_bytes = rows_to_csv_bytes(merged_rows)
    with open(tmp_path, "wb") as f:
        f.write(csv_bytes)

    return jsonify({
        "token":      token,
        "stats":      stats,
        "issues":     issues,
        "preview":    [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in merged_rows[:20]
        ],
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
        # Fall back to temp file if store was cleared
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
        # Load from temp file (no reject support in this path)
        rows = None

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

    def _find(keywords):
        for kw in keywords:
            for col in df.columns:
                if kw in col:
                    return col
        return None

    target_fields = [
        {"key": "title",          "label": "Story Title",      "required": True,  "keywords": ["story title", "title", "summary"]},
        {"key": "description",    "label": "Story Description", "required": False, "keywords": ["story description", "description", "desc"]},
        {"key": "waf_category",   "label": "WAF Category",      "required": False, "keywords": ["waf category", "waf_category", "category"]},
        {"key": "waf_color",      "label": "WAF Color",         "required": False, "keywords": ["waf color", "waf_color", "color"]},
        {"key": "run_change",     "label": "Run/Change",        "required": False, "keywords": ["run/change", "run_change", "run change"]},
        {"key": "subcategory",    "label": "Sub-Category",      "required": False, "keywords": ["sub-category", "subcategory", "waf sub"]},
        {"key": "confidence",     "label": "Confidence",        "required": False, "keywords": ["confidence", "conf"]},
        {"key": "team",           "label": "Team",              "required": False, "keywords": ["team", "squad", "group"]},
        {"key": "epic",           "label": "Epic",              "required": False, "keywords": ["epic", "initiative"]},
        {"key": "parent_feature", "label": "Parent Feature",    "required": False, "keywords": ["parent feature", "feature", "capability"]},
        {"key": "timestamp",      "label": "Timestamp",         "required": False, "keywords": ["timestamp", "date", "created"]},
        {"key": "story_id",       "label": "Story ID",          "required": False, "keywords": ["story id", "story_id", "issue key"]},
        {"key": "feature_id",     "label": "Feature ID",        "required": False, "keywords": ["feature id", "feature_id", "feature key"]},
        {"key": "epic_id",        "label": "Epic ID",           "required": False, "keywords": ["epic id", "epic_id", "epic key", "epic link"]},
    ]
    suggested    = {f["key"]: (_find(f["keywords"]) or "") for f in target_fields}
    sample_rows  = [{col: str(row.get(col, "")) for col in df.columns}
                    for _, row in df.head(3).iterrows()]
    preview_id   = str(uuid.uuid4())
    _preview_store[preview_id] = {
        "df": df, "filename": dest_name, "ext": "csv",
        "filepath": dest_path, "created": _time.time(),
    }

    return jsonify({
        "success":          True,
        "filename":         dest_name,
        "file_columns":     list(df.columns),
        "original_columns": original_columns,
        "suggested_mappings": suggested,
        "target_fields":    [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in target_fields],
        "sample_rows":      sample_rows,
        "total_rows":       len(df),
        "preview_id":       preview_id,
    })
