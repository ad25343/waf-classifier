"""
WAF Classifier — Database helpers (SQLite).
Extracted from app.py.

NOTE: close_db() remains in app.py because it needs the Flask app object
for the @app.teardown_appcontext decorator.
"""

import sqlite3
from datetime import datetime
from flask import g

from config import DB_PATH


# ── SQLite Database ────────────────────────────────────────────────────

def get_db():
    """Get database connection for current request."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            story_title TEXT NOT NULL,
            story_description TEXT,
            waf_category TEXT NOT NULL,
            waf_subcategory TEXT,
            waf_color TEXT,
            run_change TEXT,
            confidence TEXT,
            was_mismatch INTEGER DEFAULT 0,
            original_tag TEXT,
            approved INTEGER DEFAULT 0,
            team TEXT DEFAULT 'default',
            user_name TEXT,
            epic TEXT DEFAULT '',
            parent_feature TEXT DEFAULT '',
            upload_id INTEGER DEFAULT NULL,
            story_id TEXT DEFAULT '',
            feature_id TEXT DEFAULT '',
            epic_id TEXT DEFAULT '',
            story_points TEXT DEFAULT '',
            original_color TEXT DEFAULT '',
            waf_reasoning TEXT DEFAULT '',
            pi_number TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_start TEXT NOT NULL,
            session_end TEXT,
            stories_classified INTEGER DEFAULT 0,
            mismatches_found INTEGER DEFAULT 0,
            approvals INTEGER DEFAULT 0,
            team TEXT DEFAULT 'default'
        );

        CREATE TABLE IF NOT EXISTS upload_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uploaded_at TEXT NOT NULL,
            filename TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            imported_count INTEGER DEFAULT 0,
            file_type TEXT DEFAULT '',
            status TEXT DEFAULT 'completed'
        );
    """)
    # Add epic columns if they don't exist (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN epic TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN parent_feature TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN upload_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE upload_history ADD COLUMN results_json TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN story_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN feature_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN epic_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN story_points TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN original_color TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN waf_reasoning TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE classifications ADD COLUMN pi_number TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    # Story quality scores table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scored_at TEXT NOT NULL,
            classification_id INTEGER NOT NULL,
            upload_id INTEGER,
            domain TEXT DEFAULT 'data_reporting',
            overall_score REAL DEFAULT 0,
            passed_count INTEGER DEFAULT 0,
            total_count INTEGER DEFAULT 9,
            criteria_json TEXT DEFAULT '{}',
            story_title TEXT DEFAULT '',
            team TEXT DEFAULT '',
            story_id TEXT DEFAULT '',
            run_id TEXT DEFAULT '',
            job_number INTEGER DEFAULT 0
        )
    """)

    # Quality scoring run history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            job_number INTEGER DEFAULT 0,
            scored_at TEXT NOT NULL,
            upload_id INTEGER,
            upload_filename TEXT DEFAULT '',
            domain TEXT DEFAULT 'data_reporting',
            teams_json TEXT DEFAULT '[]',
            story_count INTEGER DEFAULT 0,
            avg_score REAL DEFAULT 0,
            ready_count INTEGER DEFAULT 0,
            needs_work_count INTEGER DEFAULT 0,
            not_ready_count INTEGER DEFAULT 0
        )
    """)

    # WAF Definition Versions — named, auditable snapshots
    conn.execute("""
        CREATE TABLE IF NOT EXISTS waf_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            author TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            row_count INTEGER DEFAULT 0
        )
    """)

    # Ground Truth Versions — named, auditable snapshots
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gt_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            author TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            row_count INTEGER DEFAULT 0
        )
    """)

    # Migration: track which versions were used for each upload batch
    try:
        conn.execute("ALTER TABLE upload_history ADD COLUMN waf_version_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE upload_history ADD COLUMN gt_version_id INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE story_quality_scores ADD COLUMN run_id TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE story_quality_scores ADD COLUMN job_number INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # FTS5 full-text search index — drop and recreate if schema is outdated
    fts_cols = {r[0] for r in conn.execute(
        "SELECT name FROM pragma_table_info('classifications_fts')"
    ).fetchall()} if conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='classifications_fts'"
    ).fetchone() else set()

    if 'story_id' not in fts_cols:
        # Drop old FTS table and triggers, recreate with full ID fields
        conn.executescript("""
            DROP TABLE IF EXISTS classifications_fts;
            DROP TRIGGER IF EXISTS classifications_fts_ai;
            DROP TRIGGER IF EXISTS classifications_fts_ad;
        """)

    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS classifications_fts USING fts5(
            story_title,
            story_description,
            waf_category,
            waf_color,
            team,
            epic,
            parent_feature,
            confidence,
            story_id,
            feature_id,
            epic_id,
            pi_number,
            content='classifications',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS classifications_fts_ai
        AFTER INSERT ON classifications BEGIN
            INSERT INTO classifications_fts(
                rowid, story_title, story_description, waf_category,
                waf_color, team, epic, parent_feature, confidence,
                story_id, feature_id, epic_id, pi_number
            ) VALUES (
                new.id, new.story_title, new.story_description, new.waf_category,
                new.waf_color, new.team, new.epic, new.parent_feature, new.confidence,
                new.story_id, new.feature_id, new.epic_id, new.pi_number
            );
        END;

        CREATE TRIGGER IF NOT EXISTS classifications_fts_ad
        AFTER DELETE ON classifications BEGIN
            INSERT INTO classifications_fts(
                classifications_fts, rowid, story_title, story_description,
                waf_category, waf_color, team, epic, parent_feature, confidence,
                story_id, feature_id, epic_id, pi_number
            ) VALUES (
                'delete', old.id, old.story_title, old.story_description,
                old.waf_category, old.waf_color, old.team, old.epic,
                old.parent_feature, old.confidence,
                old.story_id, old.feature_id, old.epic_id, old.pi_number
            );
        END;
    """)

    # Rebuild FTS index from existing classifications (idempotent)
    try:
        conn.execute("INSERT INTO classifications_fts(classifications_fts) VALUES('rebuild')")
    except Exception:
        pass

    # Settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    # Classification Disputes table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS disputes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            story_title TEXT DEFAULT '',
            story_description TEXT DEFAULT '',
            ai_category TEXT DEFAULT '',
            ai_color TEXT DEFAULT '',
            ai_confidence TEXT DEFAULT '',
            ai_reasoning TEXT DEFAULT '',
            user_comment TEXT DEFAULT '',
            suggested_category TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            reviewed_at TEXT DEFAULT NULL,
            reviewer_notes TEXT DEFAULT '',
            resolved_category TEXT DEFAULT '',
            resolved_color TEXT DEFAULT '',
            gt_updated INTEGER DEFAULT 0,
            waf_flagged INTEGER DEFAULT 0,
            team TEXT DEFAULT '',
            epic TEXT DEFAULT '',
            story_id TEXT DEFAULT '',
            pi_number TEXT DEFAULT ''
        )
    """)
    # Migrations for disputes table columns (for existing DBs)
    for _col, _defn in [
        ("story_title", "TEXT DEFAULT ''"),
        ("story_description", "TEXT DEFAULT ''"),
        ("ai_category", "TEXT DEFAULT ''"),
        ("ai_color", "TEXT DEFAULT ''"),
        ("ai_confidence", "TEXT DEFAULT ''"),
        ("ai_reasoning", "TEXT DEFAULT ''"),
        ("user_comment", "TEXT DEFAULT ''"),
        ("suggested_category", "TEXT DEFAULT ''"),
        ("status", "TEXT DEFAULT 'pending'"),
        ("reviewed_at", "TEXT DEFAULT NULL"),
        ("reviewer_notes", "TEXT DEFAULT ''"),
        ("resolved_category", "TEXT DEFAULT ''"),
        ("resolved_color", "TEXT DEFAULT ''"),
        ("gt_updated", "INTEGER DEFAULT 0"),
        ("waf_flagged", "INTEGER DEFAULT 0"),
        ("team", "TEXT DEFAULT ''"),
        ("epic", "TEXT DEFAULT ''"),
        ("story_id", "TEXT DEFAULT ''"),
        ("pi_number", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE disputes ADD COLUMN {_col} {_defn}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    # Default settings
    defaults = {
        "sync_batch_size": "25",
        "async_batch_size": "50",
        "max_concurrent_workers": "5",
        "rate_limit_per_minute": "5",
    }
    for k, v in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (k, v, datetime.now().isoformat())
        )
    conn.commit()
    conn.close()


# ── Settings Cache ────────────────────────────────────────────────────
_settings_cache: dict = {}
_settings_cache_loaded = False


def get_setting(key: str, default: str = "") -> str:
    """Read a setting from DB with in-memory cache."""
    global _settings_cache, _settings_cache_loaded
    if not _settings_cache_loaded:
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            _settings_cache = {r[0]: r[1] for r in rows}
            conn.close()
            _settings_cache_loaded = True
        except Exception:
            return default
    return _settings_cache.get(key, default)


def set_setting(key: str, value: str):
    """Write a setting to DB and update cache."""
    global _settings_cache
    from datetime import datetime as _dt
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, _dt.now().isoformat())
    )
    conn.commit()
    conn.close()
    _settings_cache[key] = value


def _refresh_settings_cache():
    """Force-reload settings from DB."""
    global _settings_cache, _settings_cache_loaded
    _settings_cache_loaded = False
    get_setting("_dummy")


def save_classification(title, description, category, subcategory, color,
                        run_change, confidence, was_mismatch=False,
                        original_tag="", approved=False, team="default",
                        epic="", parent_feature="",
                        story_id="", feature_id="", epic_id="",
                        story_points="", original_color="", waf_reasoning="",
                        pi_number=""):
    """Save a classification to the database."""
    db = get_db()
    db.execute(
        """INSERT INTO classifications
           (timestamp, story_title, story_description, waf_category,
            waf_subcategory, waf_color, run_change, confidence,
            was_mismatch, original_tag, approved, team, epic, parent_feature,
            story_id, feature_id, epic_id, story_points, original_color, waf_reasoning,
            pi_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().isoformat(), title, description, category,
         subcategory, color, run_change, confidence,
         1 if was_mismatch else 0, original_tag, 1 if approved else 0, team,
         epic, parent_feature, story_id, feature_id, epic_id, story_points,
         original_color, waf_reasoning, pi_number)
    )
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]
