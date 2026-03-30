"""
WAF Classifier — File Merger Blueprint
Merges 3 JIRA export files (Epic, Feature, Story) into the canonical WAF import format.
Purely a file transformation utility — no DB writes.
"""

import os
import re
import tempfile
import uuid

import pandas as pd
from flask import Blueprint, request, jsonify, send_file

merge_bp = Blueprint("merge_bp", __name__)

# ── WAF Color map ─────────────────────────────────────────────────────────────
WAF_COLOR_MAP = {
    "ktlo": "GRAY",
    "keep the lights": "GRAY",
    "regulatory": "RED",
    "reg mandated": "RED",
    "revenue": "GREEN",
    "efficiency": "BLUE",
    "operational": "BLUE",
    "new capability": "ORANGE",
    "new feature": "ORANGE",
    "tech debt": "YELLOW",
    "technical debt": "YELLOW",
    "security": "PURPLE",
    "data": "TEAL",
}

# ── Column keyword definitions ─────────────────────────────────────────────────
EPIC_KEYWORDS = {
    "id_col":   ["jira saas epic#", "epic#", "epic key", "epic id", "epic number"],
    "name_col": ["summary", "epic summary", "epic name", "epic title"],
    "waf_col":  ["work alignment framework", "work alignment", "waf"],
}

FEATURE_KEYWORDS = {
    "id_col":     ["jira saas feature key", "feature key", "feature id"],
    "name_col":   ["feature summary", "feature name", "summary"],
    "epic_col":   ["parent epic number", "parent epic", "epic number", "epic#"],
    "team_col":   ["team of teams", "team"],
    "waf_col":    ["work alignment", "waf derived", "work category", "waf"],
}

STORY_KEYWORDS = {
    "id_col":         ["story #", "story#", "story number", "issue key", "key"],
    "title_col":      ["story name", "summary", "title", "name"],
    "feature_col":    ["parent feature", "feature key", "feature#", "feature"],
    "team_col":       ["teams", "team"],
    "waf_col":        ["waf derived", "work alignment", "waf"],
    "timestamp_col":  ["resolved date", "created", "date", "timestamp"],
    "status_col":     ["status"],
}

OUTPUT_COLUMNS = [
    "Epic ID",
    "Feature ID",
    "Story ID",
    "Epic",
    "Parent Feature",
    "Story Title",
    "Story Description",
    "Team",
    "WAF Category",
    "WAF Color",
    "Sub-Category",
    "Confidence",
    "Run/Change",
    "Timestamp",
    "Issue Key",
]


def find_col(headers, keywords):
    """
    Keyword-priority column finder.
    Tries each keyword against all column headers; first match wins.
    Matching is substring, case-insensitive.
    """
    h_map = {h.lower().strip(): h for h in headers}
    for kw in keywords:
        for h_lower, h_orig in h_map.items():
            if kw in h_lower:
                return h_orig
    return None


def resolve_waf_color(waf_value):
    """Map a WAF category string to its color using partial matching."""
    if not waf_value or pd.isna(waf_value):
        return ""
    val = str(waf_value).lower().strip()
    for key, color in WAF_COLOR_MAP.items():
        if key in val:
            return color
    return ""


def read_file(file_storage):
    """Read an uploaded file (CSV or XLSX) into a DataFrame."""
    filename = file_storage.filename or ""
    ext = os.path.splitext(filename)[-1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(file_storage)
    else:
        # Try UTF-8 first, fall back to latin-1
        try:
            return pd.read_csv(file_storage, encoding="utf-8")
        except UnicodeDecodeError:
            file_storage.seek(0)
            return pd.read_csv(file_storage, encoding="latin-1")


def detect_column_map(df_epic, df_feature, df_story):
    """Return a dict of detected column names for each file."""
    epic_cols = list(df_epic.columns)
    feat_cols = list(df_feature.columns)
    story_cols = list(df_story.columns)

    epic_map = {k: find_col(epic_cols, v) for k, v in EPIC_KEYWORDS.items()}
    feature_map = {k: find_col(feat_cols, v) for k, v in FEATURE_KEYWORDS.items()}
    story_map = {k: find_col(story_cols, v) for k, v in STORY_KEYWORDS.items()}

    return {"epic": epic_map, "feature": feature_map, "story": story_map}


def safe_str(val):
    """Convert a value to a clean string, treating NaN/None as empty."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def merge_files(df_epic, df_feature, df_story, col_map):
    """
    Core merge logic.
    Returns (merged_rows: list[dict], stats: dict)
    """
    em = col_map["epic"]
    fm = col_map["feature"]
    sm = col_map["story"]

    # ── Build epic lookup: epic_id -> {name, waf} ─────────────────────────────
    epic_lookup = {}
    if em["id_col"]:
        for _, row in df_epic.iterrows():
            eid = safe_str(row.get(em["id_col"], ""))
            if eid:
                epic_lookup[eid] = {
                    "name": safe_str(row.get(em["name_col"], "")) if em["name_col"] else "",
                    "waf":  safe_str(row.get(em["waf_col"],  "")) if em["waf_col"]  else "",
                }

    # ── Build feature lookup: feature_id -> {name, parent_epic_id, team, waf} ─
    feature_lookup = {}
    if fm["id_col"]:
        for _, row in df_feature.iterrows():
            fid = safe_str(row.get(fm["id_col"], ""))
            if fid:
                feature_lookup[fid] = {
                    "name":          safe_str(row.get(fm["name_col"],  "")) if fm["name_col"]  else "",
                    "parent_epic_id":safe_str(row.get(fm["epic_col"],  "")) if fm["epic_col"]  else "",
                    "team":          safe_str(row.get(fm["team_col"],  "")) if fm["team_col"]  else "",
                    "waf":           safe_str(row.get(fm["waf_col"],   "")) if fm["waf_col"]   else "",
                }

    merged_rows = []
    unmatched_features = 0
    unmatched_epics = 0

    for _, row in df_story.iterrows():
        story_id  = safe_str(row.get(sm["id_col"],      "")) if sm["id_col"]      else ""
        title     = safe_str(row.get(sm["title_col"],   "")) if sm["title_col"]   else ""
        feat_ref  = safe_str(row.get(sm["feature_col"], "")) if sm["feature_col"] else ""
        s_team    = safe_str(row.get(sm["team_col"],    "")) if sm["team_col"]    else ""
        s_waf     = safe_str(row.get(sm["waf_col"],     "")) if sm["waf_col"]     else ""
        timestamp = safe_str(row.get(sm["timestamp_col"],"")) if sm["timestamp_col"] else ""

        # Resolve feature
        feat_data = feature_lookup.get(feat_ref, {})
        feat_name = feat_data.get("name", "")
        f_team    = feat_data.get("team", "")
        f_waf     = feat_data.get("waf",  "")
        epic_ref  = feat_data.get("parent_epic_id", "")

        if feat_ref and not feat_data:
            unmatched_features += 1

        # Resolve epic
        epic_data = epic_lookup.get(epic_ref, {})
        epic_name = epic_data.get("name", "")
        e_waf     = epic_data.get("waf",  "")

        if epic_ref and not epic_data:
            unmatched_epics += 1

        # WAF priority: story > feature > epic
        waf_category = s_waf or f_waf or e_waf

        # Team priority: story > feature
        team = s_team or f_team

        waf_color = resolve_waf_color(waf_category)

        merged_rows.append({
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
        })

    stats = {
        "epics":              len(epic_lookup),
        "features":           len(feature_lookup),
        "stories":            len(df_story),
        "matched":            len(merged_rows) - unmatched_features,
        "unmatched_features": unmatched_features,
        "unmatched_epics":    unmatched_epics,
    }

    return merged_rows, stats


# ── Endpoints ─────────────────────────────────────────────────────────────────

@merge_bp.route("/api/merge/process", methods=["POST"])
def merge_process():
    """
    Accept 3 uploaded files (epic_file, feature_file, story_file),
    merge them, return JSON with preview + token.
    """
    errors = []
    for name in ("epic_file", "feature_file", "story_file"):
        if name not in request.files:
            errors.append(f"Missing file: {name}")
        elif request.files[name].filename == "":
            errors.append(f"Empty filename for: {name}")
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    try:
        df_epic    = read_file(request.files["epic_file"])
        df_feature = read_file(request.files["feature_file"])
        df_story   = read_file(request.files["story_file"])
    except Exception as exc:
        return jsonify({"error": f"Failed to read uploaded files: {exc}"}), 400

    col_map = detect_column_map(df_epic, df_feature, df_story)

    try:
        merged_rows, stats = merge_files(df_epic, df_feature, df_story, col_map)
    except Exception as exc:
        return jsonify({"error": f"Merge failed: {exc}"}), 500

    # Save temp file
    token = uuid.uuid4().hex[:8]
    tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
    df_out = pd.DataFrame(merged_rows, columns=OUTPUT_COLUMNS)
    df_out.to_csv(tmp_path, index=False)

    # Preview: first 20 rows as list of dicts
    preview = merged_rows[:20]

    return jsonify({
        "token":      token,
        "stats":      stats,
        "preview":    preview,
        "columns":    OUTPUT_COLUMNS,
        "column_map": col_map,
    })


@merge_bp.route("/api/merge/download/<token>", methods=["GET"])
def merge_download(token):
    """Return the merged CSV file as a browser download."""
    if not re.fullmatch(r"[0-9a-f]{8}", token):
        return jsonify({"error": "Invalid token"}), 400
    tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
    if not os.path.exists(tmp_path):
        return jsonify({"error": "File not found or expired"}), 404
    return send_file(
        tmp_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"waf_merged_{token}.csv",
    )


@merge_bp.route("/api/merge/send-to-classifier/<token>", methods=["POST"])
def merge_send_to_classifier(token):
    """
    Run the full bulk-verify preview on the merged temp file and return
    the complete preview JSON (same shape as /api/bulk-verify/preview).
    The frontend stores this in sessionStorage and redirects to /history,
    which reads sessionStorage and auto-triggers the mapping step.
    """
    if not re.fullmatch(r"[0-9a-f]{8}", token):
        return jsonify({"error": "Invalid token"}), 400

    tmp_path = os.path.join(tempfile.gettempdir(), f"waf_merge_{token}.csv")
    if not os.path.exists(tmp_path):
        return jsonify({"error": "File not found or expired"}), 404

    # Build a clean filename from the job name (fallback to token)
    raw_job_name = request.form.get("job_name", "").strip()
    if raw_job_name:
        # Sanitize: keep alphanumeric, spaces, hyphens, underscores
        safe_job = re.sub(r"[^\w\s\-]", "", raw_job_name).strip()
        safe_job = re.sub(r"\s+", "-", safe_job)[:80]
        dest_name = f"{safe_job}.csv" if safe_job else f"waf_merged_{token}.csv"
    else:
        dest_name = f"waf_merged_{token}.csv"

    # Copy into uploads folder
    from config import UPLOAD_FOLDER
    import shutil
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    dest_path = os.path.join(UPLOAD_FOLDER, dest_name)
    shutil.copy2(tmp_path, dest_path)

    # Run the same column-detection logic as /api/bulk-verify/preview
    import pandas as pd
    import time as _time
    from state import _preview_store

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
        {"key": "title",          "label": "Story Title",      "required": True,  "keywords": ["story title", "title", "summary", "story", "name"]},
        {"key": "description",    "label": "Story Description", "required": False, "keywords": ["story description", "description", "desc", "detail", "body"]},
        {"key": "waf_category",   "label": "WAF Category",      "required": False, "keywords": ["waf category", "waf_category", "category"]},
        {"key": "waf_color",      "label": "WAF Color",         "required": False, "keywords": ["waf color", "waf_color", "color"]},
        {"key": "run_change",     "label": "Run/Change",        "required": False, "keywords": ["run/change", "run_change", "run change"]},
        {"key": "subcategory",    "label": "Sub-Category",      "required": False, "keywords": ["sub-category", "subcategory", "waf sub"]},
        {"key": "confidence",     "label": "Confidence",        "required": False, "keywords": ["confidence", "conf"]},
        {"key": "team",           "label": "Team",              "required": False, "keywords": ["team", "squad", "group"]},
        {"key": "epic",           "label": "Epic",              "required": False, "keywords": ["epic", "initiative", "program"]},
        {"key": "parent_feature", "label": "Parent Feature",    "required": False, "keywords": ["parent feature", "feature", "capability"]},
        {"key": "timestamp",      "label": "Timestamp",         "required": False, "keywords": ["timestamp", "date", "created"]},
        {"key": "story_id",       "label": "Story ID",          "required": False, "keywords": ["story id", "story_id", "issue key", "ticket"]},
        {"key": "feature_id",     "label": "Feature ID",        "required": False, "keywords": ["feature id", "feature_id", "feature key"]},
        {"key": "epic_id",        "label": "Epic ID",           "required": False, "keywords": ["epic id", "epic_id", "epic key", "epic link"]},
    ]
    suggested = {f["key"]: (_find(f["keywords"]) or "") for f in target_fields}
    sample_rows = [{col: str(row.get(col, "")) for col in df.columns}
                   for _, row in df.head(3).iterrows()]

    preview_id = str(uuid.uuid4())
    _preview_store[preview_id] = {
        "df": df,
        "filename": dest_name,
        "ext": "csv",
        "filepath": dest_path,
        "created": _time.time(),
    }

    return jsonify({
        "success": True,
        "filename": dest_name,
        "file_columns": list(df.columns),
        "original_columns": original_columns,
        "suggested_mappings": suggested,
        "target_fields": [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in target_fields],
        "sample_rows": sample_rows,
        "total_rows": len(df),
        "preview_id": preview_id,
    })
