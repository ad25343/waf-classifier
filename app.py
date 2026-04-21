"""
WAF Category Classifier - Backend
Helps scrum teams correctly classify JIRA stories into WAF categories
using Claude AI for intelligent recommendation and mismatch detection.
Supports ground truth examples for calibration.
"""

import os
import shutil

from flask import Flask, g

# ── Foundation modules ────────────────────────────────────────────
from config import AI_BACKEND, AI_MODEL, DB_PATH, BASELINE_DIR
from database import init_db
from state import waf_store, ground_truth_store
from waf_core import parse_waf_file, parse_ground_truth

# ── Flask app ─────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload
app.secret_key = os.urandom(24)


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── Register blueprints ──────────────────────────────────────────
from routes.pages import pages_bp
from routes.classify import classify_bp
from routes.settings_api import settings_bp
from routes.analytics import analytics_bp
from routes.verify import verify_bp
from routes.lineage import lineage_bp

app.register_blueprint(pages_bp)
app.register_blueprint(classify_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(verify_bp)
app.register_blueprint(lineage_bp)

# Register teams blueprint if available
try:
    from routes.teams import teams_bp
    app.register_blueprint(teams_bp)
except ImportError:
    pass  # teams.py not yet created

from routes.merge import merge_bp
app.register_blueprint(merge_bp)

from routes.quality import quality_bp
app.register_blueprint(quality_bp)


# ── Startup ──────────────────────────────────────────────────────
def auto_load_sample_data():
    """Auto-load WAF definitions and ground truth on startup.
    Priority: 1) last user-uploaded file (from DB), 2) test-data/ defaults.
    """
    from database import get_setting
    test_dir = os.path.join(os.path.dirname(__file__), "test-data")

    # ── WAF Definitions ──────────────────────────────────────────────
    waf_file = get_setting("active_waf_path") or os.path.join(test_dir, "waf-definitions.csv")
    if os.path.exists(waf_file):
        try:
            filename = os.path.basename(waf_file)
            text, categories, df = parse_waf_file(waf_file, filename)
            waf_store["definitions"] = df
            waf_store["raw_text"] = text
            waf_store["filename"] = filename
            waf_store["categories"] = categories
            print(f"  Auto-loaded WAF definitions ({filename}): {len(categories)} categories")
        except Exception as e:
            print(f"  Warning: Failed to auto-load WAF definitions: {e}")
    else:
        print("  WAF definitions not found — upload via Settings.")

    # ── Ground Truth ─────────────────────────────────────────────────
    gt_file = get_setting("active_gt_path") or os.path.join(test_dir, "sample-ground-truth.csv")
    if os.path.exists(gt_file):
        try:
            filename = os.path.basename(gt_file)
            examples, stats, col_map = parse_ground_truth(gt_file, filename)
            ground_truth_store["loaded"] = True
            ground_truth_store["filename"] = filename
            ground_truth_store["examples"] = examples
            ground_truth_store["example_count"] = len(examples)
            ground_truth_store["stats"] = stats
            ground_truth_store["raw_text"] = f"{len(examples)} examples across {len(stats)} categories"
            print(f"  Auto-loaded ground truth ({filename}): {len(examples)} examples")
        except Exception as e:
            print(f"  Warning: Failed to auto-load ground truth: {e}")
    else:
        print("  Ground truth not found — upload via Settings.")

    # Save a "default" baseline if it doesn't exist yet
    default_waf = os.path.join(BASELINE_DIR, "waf-definitions_baseline_default.csv")
    default_gt = os.path.join(BASELINE_DIR, "ground-truth_baseline_default.csv")
    if not os.path.exists(default_waf) or not os.path.exists(default_gt):
        waf_src = os.path.join(test_dir, "waf-definitions.csv")
        gt_src = os.path.join(test_dir, "sample-ground-truth.csv")
        if os.path.exists(waf_src) and not os.path.exists(default_waf):
            shutil.copy2(waf_src, default_waf)
        if os.path.exists(gt_src) and not os.path.exists(default_gt):
            shutil.copy2(gt_src, default_gt)
        print(f"  Default baseline saved to {BASELINE_DIR}")

    # Seed the version library tables if they're empty (first launch)
    import sqlite3 as _sqlite3
    from datetime import datetime as _dt
    _conn = _sqlite3.connect(DB_PATH)

    waf_ver_dir = os.path.join(BASELINE_DIR, "waf")
    gt_ver_dir  = os.path.join(BASELINE_DIR, "gt")
    os.makedirs(waf_ver_dir, exist_ok=True)
    os.makedirs(gt_ver_dir,  exist_ok=True)

    waf_count = _conn.execute("SELECT COUNT(*) FROM waf_versions").fetchone()[0]
    if waf_count == 0 and os.path.exists(default_waf):
        # Copy into the versioned sub-dir so the path stays consistent
        dest = os.path.join(waf_ver_dir, "waf_Default_Baseline.csv")
        if not os.path.exists(dest):
            shutil.copy2(default_waf, dest)
        try:
            import pandas as _pd
            row_count = len(_pd.read_csv(dest))
        except Exception:
            row_count = 0
        _conn.execute(
            "INSERT INTO waf_versions (name, author, notes, filename, filepath, created_at, is_default, row_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            ("Default Baseline", "System", "Auto-created on first launch",
             "waf_Default_Baseline.csv", dest, _dt.now().isoformat(), row_count)
        )
        _conn.commit()
        print("  Seeded default WAF version into version library")

    gt_count = _conn.execute("SELECT COUNT(*) FROM gt_versions").fetchone()[0]
    if gt_count == 0 and os.path.exists(default_gt):
        dest = os.path.join(gt_ver_dir, "gt_Default_Baseline.csv")
        if not os.path.exists(dest):
            shutil.copy2(default_gt, dest)
        try:
            import pandas as _pd
            row_count = len(_pd.read_csv(dest))
        except Exception:
            row_count = 0
        _conn.execute(
            "INSERT INTO gt_versions (name, author, notes, filename, filepath, created_at, is_default, row_count) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            ("Default Baseline", "System", "Auto-created on first launch",
             "gt_Default_Baseline.csv", dest, _dt.now().isoformat(), row_count)
        )
        _conn.commit()
        print("  Seeded default GT version into version library")

    _conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n{'='*60}")
    print(f"  WAF Category Classifier")
    print(f"  Running at: http://localhost:{port}")
    print(f"  Analytics:  http://localhost:{port}/history")
    if AI_BACKEND == "anthropic":
        print(f"  AI backend: Anthropic API (key configured)")
    else:
        aws_region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
        print(f"  AI backend: AWS Bedrock ({aws_region}) — model: {AI_MODEL}")
    init_db()
    print(f"  Database initialized: {DB_PATH}")
    auto_load_sample_data()
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
