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
from database import get_db, get_setting, _refresh_settings_cache
from waf_core import parse_waf_file, parse_ground_truth

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
