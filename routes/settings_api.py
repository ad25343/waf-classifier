"""
WAF Classifier — Settings, Ground Truth, Baseline, and WAF Definitions API routes.
Blueprint: settings_bp
"""

import os
import shutil
from datetime import datetime

import pandas as pd
from flask import Blueprint, request, jsonify

from state import waf_store, ground_truth_store
from config import BASELINE_DIR, UPLOAD_FOLDER
from database import get_db, get_setting, set_setting, _refresh_settings_cache
from waf_core import parse_waf_file, parse_ground_truth

# Sub-directories for named version files
WAF_VER_DIR = os.path.join(BASELINE_DIR, "waf")
GT_VER_DIR  = os.path.join(BASELINE_DIR, "gt")
os.makedirs(WAF_VER_DIR, exist_ok=True)
os.makedirs(GT_VER_DIR,  exist_ok=True)

settings_bp = Blueprint("settings_bp", __name__)


@settings_bp.route("/api/settings", methods=["GET"])
def get_settings():
    """Return all settings."""
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in rows}
    return jsonify({"settings": settings})


@settings_bp.route("/api/settings", methods=["PUT"])
def update_settings():
    """Update settings with validation."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    VALIDATIONS = {
        "sync_batch_size": (1, 200),
        "async_batch_size": (1, 200),
        "max_concurrent_workers": (1, 20),
        "rate_limit_per_minute": (1, 60),
    }

    db = get_db()
    now = datetime.now().isoformat()
    errors = []
    for key, value in data.items():
        if key not in VALIDATIONS:
            continue
        try:
            val = int(value)
            lo, hi = VALIDATIONS[key]
            if val < lo or val > hi:
                errors.append(f"{key} must be between {lo} and {hi}")
                continue
            db.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, str(val), now)
            )
        except (ValueError, TypeError):
            errors.append(f"{key} must be an integer")

    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    db.commit()
    _refresh_settings_cache()

    rows = db.execute("SELECT key, value FROM settings").fetchall()
    settings = {r["key"]: r["value"] for r in rows}
    return jsonify({"success": True, "settings": settings})


@settings_bp.route("/api/ground-truth", methods=["GET"])
def get_ground_truth():
    """Return current ground truth examples."""
    return jsonify({
        "loaded": ground_truth_store["loaded"],
        "filename": ground_truth_store["filename"],
        "example_count": ground_truth_store["example_count"],
        "stats": ground_truth_store["stats"],
        "examples": ground_truth_store["examples"],
    })


@settings_bp.route("/api/ground-truth/<int:idx>", methods=["PUT"])
def update_ground_truth_row(idx):
    """Update a single ground truth example by index."""
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400
    examples = ground_truth_store["examples"]
    if idx < 0 or idx >= len(examples):
        return jsonify({"error": "Index out of range"}), 404
    # Update fields
    for key in ["title", "description", "category", "subcategory", "color", "run_change"]:
        if key in data:
            examples[idx][key] = data[key]
    # Recalculate stats
    stats = {}
    for ex in examples:
        cat = ex.get("category", "Unknown")
        stats[cat] = stats.get(cat, 0) + 1
    ground_truth_store["stats"] = stats
    return jsonify({"success": True, "example": examples[idx]})


@settings_bp.route("/api/ground-truth/add", methods=["POST"])
def add_ground_truth_row():
    """Add a new ground truth example."""
    data = request.get_json(force=True)
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400
    example = {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "subcategory": data.get("subcategory", ""),
        "color": data.get("color", ""),
        "run_change": data.get("run_change", ""),
    }
    ground_truth_store["examples"].append(example)
    ground_truth_store["example_count"] = len(ground_truth_store["examples"])
    ground_truth_store["loaded"] = True
    # Recalculate stats
    stats = {}
    for ex in ground_truth_store["examples"]:
        cat = ex.get("category", "Unknown")
        stats[cat] = stats.get(cat, 0) + 1
    ground_truth_store["stats"] = stats
    return jsonify({"success": True, "example": example, "example_count": ground_truth_store["example_count"]})


@settings_bp.route("/api/ground-truth/<int:idx>", methods=["DELETE"])
def delete_ground_truth_row(idx):
    """Delete a ground truth example by index."""
    examples = ground_truth_store["examples"]
    if idx < 0 or idx >= len(examples):
        return jsonify({"error": "Index out of range"}), 404
    removed = examples.pop(idx)
    ground_truth_store["example_count"] = len(examples)
    if not examples:
        ground_truth_store["loaded"] = False
    stats = {}
    for ex in examples:
        cat = ex.get("category", "Unknown")
        stats[cat] = stats.get(cat, 0) + 1
    ground_truth_store["stats"] = stats
    return jsonify({"success": True, "removed": removed, "example_count": len(examples)})


@settings_bp.route("/api/baseline/save", methods=["POST"])
def save_baseline():
    """Save current WAF definitions and ground truth as a baseline snapshot."""
    now = datetime.now().strftime("%Y%m%d_%H%M%S")

    saved = {}

    # Save WAF definitions
    if waf_store["definitions"] is not None:
        waf_path = os.path.join(BASELINE_DIR, f"waf-definitions_baseline_{now}.csv")
        waf_store["definitions"].to_csv(waf_path, index=False)
        saved["waf_definitions"] = waf_path
    elif waf_store["filename"]:
        src = os.path.join(UPLOAD_FOLDER, waf_store["filename"])
        if os.path.exists(src):
            dst = os.path.join(BASELINE_DIR, f"waf-definitions_baseline_{now}.csv")
            shutil.copy2(src, dst)
            saved["waf_definitions"] = dst

    # Save ground truth
    if ground_truth_store["examples"]:
        gt_path = os.path.join(BASELINE_DIR, f"ground-truth_baseline_{now}.csv")
        gt_df = pd.DataFrame(ground_truth_store["examples"])
        # Rename columns to match expected format
        col_map = {"title": "Story Title", "description": "Description", "run_change": "Run/Change",
                    "color": "WAF Color", "category": "WAF Category", "subcategory": "WAF Sub-Category"}
        gt_df = gt_df.rename(columns=col_map)
        gt_df.to_csv(gt_path, index=False)
        saved["ground_truth"] = gt_path

    if not saved:
        return jsonify({"error": "Nothing to save — no WAF definitions or ground truth loaded."}), 400

    return jsonify({"success": True, "saved": saved, "timestamp": now})


@settings_bp.route("/api/baseline/list", methods=["GET"])
def list_baselines():
    """List available baseline snapshots. Default baseline is always first."""
    baselines = []
    if os.path.exists(BASELINE_DIR):
        files = sorted(os.listdir(BASELINE_DIR), reverse=True)
        timestamps = {}
        for f in files:
            if "_baseline_" in f:
                ts = f.split("_baseline_")[1].replace(".csv", "")
                if ts not in timestamps:
                    timestamps[ts] = {"timestamp": ts, "files": [], "is_default": ts == "default"}
                timestamps[ts]["files"].append(f)
        # Put default first, then rest by timestamp descending
        default_bl = timestamps.pop("default", None)
        baselines = list(timestamps.values())
        if default_bl:
            baselines.insert(0, default_bl)
    return jsonify({"baselines": baselines})


@settings_bp.route("/api/baseline/restore", methods=["POST"])
def restore_baseline():
    """Restore WAF definitions and/or ground truth from a baseline snapshot."""
    data = request.get_json(force=True)
    ts = data.get("timestamp", "")
    if not ts:
        return jsonify({"error": "No timestamp provided"}), 400

    restored = {}

    # Restore WAF definitions
    waf_file = os.path.join(BASELINE_DIR, f"waf-definitions_baseline_{ts}.csv")
    if os.path.exists(waf_file):
        text, categories, df = parse_waf_file(waf_file, f"waf-definitions_baseline_{ts}.csv")
        waf_store["definitions"] = df
        waf_store["raw_text"] = text
        waf_store["filename"] = f"baseline_{ts}"
        waf_store["categories"] = categories
        restored["waf_definitions"] = len(categories)

    # Restore ground truth
    gt_file = os.path.join(BASELINE_DIR, f"ground-truth_baseline_{ts}.csv")
    if os.path.exists(gt_file):
        examples, stats, col_map = parse_ground_truth(gt_file, f"ground-truth_baseline_{ts}.csv")
        ground_truth_store["loaded"] = True
        ground_truth_store["filename"] = f"baseline_{ts}"
        ground_truth_store["examples"] = examples
        ground_truth_store["example_count"] = len(examples)
        ground_truth_store["stats"] = stats
        ground_truth_store["raw_text"] = f"{len(examples)} examples across {len(stats)} categories"
        restored["ground_truth"] = len(examples)

    if not restored:
        return jsonify({"error": f"No baseline files found for timestamp {ts}"}), 404

    return jsonify({"success": True, "restored": restored})


@settings_bp.route("/api/waf-definitions", methods=["GET"])
def get_waf_definitions():
    """Return loaded WAF definitions for the reference page."""
    df = waf_store["definitions"]
    if df is None:
        # No structured definitions loaded — check if raw text exists
        if waf_store["raw_text"]:
            return jsonify({"definitions": [], "loaded": True,
                            "message": "WAF definitions loaded as text (no structured data available)"})
        return jsonify({"definitions": [], "loaded": False})

    defs = []
    for _, row in df.iterrows():
        defs.append({
            "run_change": str(row.get("Run/Change", "")),
            "color": str(row.get("WAF Color", "")),
            "category": str(row.get("WAF Category", "")),
            "description": str(row.get("What This Work Is", "")),
            "decision_rule": str(row.get("How to Decide (Tag Here If...)", "")),
            "examples": str(row.get("Representative Examples", ""))
        })
    return jsonify({"definitions": defs, "loaded": True})


@settings_bp.route("/api/waf-definitions", methods=["PUT"])
def update_waf_definitions():
    """Apply inline edits to WAF definitions (updates in-memory store)."""
    data = request.get_json(force=True)
    defs = data.get("definitions", [])
    if not defs:
        return jsonify({"error": "No definitions provided"}), 400

    records = []
    for d in defs:
        records.append({
            "WAF Category":                  d.get("category", ""),
            "WAF Color":                     d.get("color", ""),
            "Run/Change":                    d.get("run_change", ""),
            "What This Work Is":             d.get("description", ""),
            "How to Decide (Tag Here If...)": d.get("decision_rule", ""),
            "Representative Examples":       d.get("examples", ""),
        })

    df = pd.DataFrame(records)
    waf_store["definitions"] = df
    waf_store["categories"]  = [c for c in df["WAF Category"].dropna().tolist() if c]
    waf_store["raw_text"]    = df.to_csv(index=False)
    waf_store["filename"]    = waf_store.get("filename", "inline-edit")
    return jsonify({"success": True, "count": len(records)})


# ── Version Library ────────────────────────────────────────────────────

def _row_count_for_file(filepath):
    """Best-effort row count for a CSV file (excludes header)."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


@settings_bp.route("/api/versions/waf", methods=["GET"])
def list_waf_versions():
    """List all saved WAF definition versions."""
    db = get_db()
    rows = db.execute(
        "SELECT id, name, author, notes, filename, created_at, is_default, row_count "
        "FROM waf_versions ORDER BY is_default DESC, created_at DESC"
    ).fetchall()
    return jsonify({"versions": [dict(r) for r in rows]})


@settings_bp.route("/api/versions/gt", methods=["GET"])
def list_gt_versions():
    """List all saved Ground Truth versions."""
    db = get_db()
    rows = db.execute(
        "SELECT id, name, author, notes, filename, created_at, is_default, row_count "
        "FROM gt_versions ORDER BY is_default DESC, created_at DESC"
    ).fetchall()
    return jsonify({"versions": [dict(r) for r in rows]})


@settings_bp.route("/api/versions/waf", methods=["POST"])
def save_waf_version():
    """Snapshot current WAF definitions as a named version."""
    data = request.get_json(force=True) or {}
    name   = data.get("name",   "").strip()
    author = data.get("author", "").strip()
    notes  = data.get("notes",  "").strip()

    if not name:
        return jsonify({"error": "Version name is required"}), 400
    if not author:
        return jsonify({"error": "Author name is required"}), 400

    now = datetime.now()
    ts  = now.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)[:50].strip().replace(" ", "_")
    filename = f"waf_{safe}_{ts}.csv"
    filepath = os.path.join(WAF_VER_DIR, filename)

    if waf_store["definitions"] is not None:
        waf_store["definitions"].to_csv(filepath, index=False)
    elif waf_store["filename"]:
        src = os.path.join(UPLOAD_FOLDER, waf_store["filename"])
        if os.path.exists(src):
            shutil.copy2(src, filepath)
        else:
            return jsonify({"error": "Active WAF file not found on disk"}), 400
    else:
        return jsonify({"error": "No WAF definitions are currently loaded"}), 400

    row_count = _row_count_for_file(filepath)
    db = get_db()
    cur = db.execute(
        "INSERT INTO waf_versions (name, author, notes, filename, filepath, created_at, row_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, author, notes, filename, filepath, now.isoformat(), row_count)
    )
    db.commit()
    return jsonify({"success": True, "id": cur.lastrowid, "name": name, "row_count": row_count})


@settings_bp.route("/api/versions/gt", methods=["POST"])
def save_gt_version():
    """Snapshot current Ground Truth as a named version."""
    data = request.get_json(force=True) or {}
    name   = data.get("name",   "").strip()
    author = data.get("author", "").strip()
    notes  = data.get("notes",  "").strip()

    if not name:
        return jsonify({"error": "Version name is required"}), 400
    if not author:
        return jsonify({"error": "Author name is required"}), 400
    if not ground_truth_store["examples"]:
        return jsonify({"error": "No Ground Truth examples are currently loaded"}), 400

    now = datetime.now()
    ts  = now.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)[:50].strip().replace(" ", "_")
    filename = f"gt_{safe}_{ts}.csv"
    filepath = os.path.join(GT_VER_DIR, filename)

    col_map = {"title": "Story Title", "description": "Description",
               "run_change": "Run/Change", "color": "WAF Color",
               "category": "WAF Category", "subcategory": "WAF Sub-Category"}
    gt_df = pd.DataFrame(ground_truth_store["examples"]).rename(columns=col_map)
    gt_df.to_csv(filepath, index=False)

    row_count = len(ground_truth_store["examples"])
    db = get_db()
    cur = db.execute(
        "INSERT INTO gt_versions (name, author, notes, filename, filepath, created_at, row_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, author, notes, filename, filepath, now.isoformat(), row_count)
    )
    db.commit()
    return jsonify({"success": True, "id": cur.lastrowid, "name": name, "row_count": row_count})


@settings_bp.route("/api/versions/waf/<int:ver_id>", methods=["DELETE"])
def delete_waf_version(ver_id):
    """Delete a WAF version (protected: cannot delete the default)."""
    db = get_db()
    row = db.execute("SELECT * FROM waf_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if row["is_default"]:
        return jsonify({"error": "The default baseline cannot be deleted"}), 400
    try:
        if os.path.exists(row["filepath"]):
            os.remove(row["filepath"])
    except Exception:
        pass
    db.execute("DELETE FROM waf_versions WHERE id=?", (ver_id,))
    db.commit()
    return jsonify({"success": True})


@settings_bp.route("/api/versions/gt/<int:ver_id>", methods=["DELETE"])
def delete_gt_version(ver_id):
    """Delete a GT version (protected: cannot delete the default)."""
    db = get_db()
    row = db.execute("SELECT * FROM gt_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if row["is_default"]:
        return jsonify({"error": "The default baseline cannot be deleted"}), 400
    try:
        if os.path.exists(row["filepath"]):
            os.remove(row["filepath"])
    except Exception:
        pass
    db.execute("DELETE FROM gt_versions WHERE id=?", (ver_id,))
    db.commit()
    return jsonify({"success": True})


@settings_bp.route("/api/versions/waf/<int:ver_id>/preview", methods=["GET"])
def preview_waf_version(ver_id):
    """Return the first 10 rows of a WAF version file."""
    db = get_db()
    row = db.execute("SELECT * FROM waf_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if not os.path.exists(row["filepath"]):
        return jsonify({"error": "Version file not found on disk"}), 404
    try:
        df = pd.read_csv(row["filepath"])
        return jsonify({
            "name": row["name"], "author": row["author"],
            "created_at": row["created_at"], "notes": row["notes"],
            "columns": list(df.columns),
            "rows": df.head(10).fillna("").astype(str).to_dict(orient="records"),
            "total_rows": len(df)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/versions/gt/<int:ver_id>/preview", methods=["GET"])
def preview_gt_version(ver_id):
    """Return the first 10 rows of a GT version file."""
    db = get_db()
    row = db.execute("SELECT * FROM gt_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if not os.path.exists(row["filepath"]):
        return jsonify({"error": "Version file not found on disk"}), 404
    try:
        df = pd.read_csv(row["filepath"])
        return jsonify({
            "name": row["name"], "author": row["author"],
            "created_at": row["created_at"], "notes": row["notes"],
            "columns": list(df.columns),
            "rows": df.head(10).fillna("").astype(str).to_dict(orient="records"),
            "total_rows": len(df)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/api/versions/waf/<int:ver_id>/activate", methods=["POST"])
def activate_waf_version(ver_id):
    """Load a WAF version as the active global store."""
    db = get_db()
    row = db.execute("SELECT * FROM waf_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if not os.path.exists(row["filepath"]):
        return jsonify({"error": "Version file not found on disk"}), 404
    text, categories, df = parse_waf_file(row["filepath"], row["filename"])
    waf_store["definitions"] = df
    waf_store["raw_text"]    = text
    waf_store["filename"]    = row["filename"]
    waf_store["categories"]  = categories
    set_setting("active_waf_path", row["filepath"])
    return jsonify({"success": True, "name": row["name"], "categories": len(categories)})


@settings_bp.route("/api/versions/gt/<int:ver_id>/activate", methods=["POST"])
def activate_gt_version(ver_id):
    """Load a GT version as the active global store."""
    db = get_db()
    row = db.execute("SELECT * FROM gt_versions WHERE id=?", (ver_id,)).fetchone()
    if not row:
        return jsonify({"error": "Version not found"}), 404
    if not os.path.exists(row["filepath"]):
        return jsonify({"error": "Version file not found on disk"}), 404
    examples, stats, _ = parse_ground_truth(row["filepath"], row["filename"])
    ground_truth_store["loaded"]        = True
    ground_truth_store["filename"]      = row["filename"]
    ground_truth_store["examples"]      = examples
    ground_truth_store["example_count"] = len(examples)
    ground_truth_store["stats"]         = stats
    ground_truth_store["raw_text"]      = f"{len(examples)} examples across {len(stats)} categories"
    set_setting("active_gt_path", row["filepath"])
    return jsonify({"success": True, "name": row["name"], "example_count": len(examples)})
