"""
Usage analytics — aggregate, anonymous tracking of:
  * API / page hits (route, method, status, response time)
  * AI token usage (input + output tokens, model, estimated cost)

NOTHING in this module touches user-level or row-level data. We only
log the feature/route fingerprint of each request and (for AI calls)
the token cost. Aggregates power the /admin/usage dashboard.

Wiring:
  - install_usage_tracking(app) — call once from app.py to register
    Flask before/after_request handlers.
  - record_token_use(...) — call from any AI-calling code site after
    a successful Anthropic response, passing the resp.usage values.
  - The admin blueprint (admin_bp) registers the /admin/usage page
    routes and /api/admin/usage/* endpoints.
"""

import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, Response, request, g, jsonify, session

from config import DB_PATH
from database import get_db


admin_bp = Blueprint("admin_bp", __name__)


# ── Feature catalog: URL pattern → human-readable feature name ───────────────
# Order matters: the first matching pattern wins. Tightest patterns first.

_FEATURE_RULES = [
    # AI calls — tagged so token costs roll up by feature
    (re.compile(r"^/api/quality/score$"),                "Backlog Quality — Score Items"),
    (re.compile(r"^/api/quality/rewrite$"),              "Backlog Quality — What Good Looks Like"),
    (re.compile(r"^/api/quality/chat$"),                 "Backlog Quality — Iterative Rewrite Chat"),
    (re.compile(r"^/api/quality/extension"),             "Backlog Quality — Domain Editor"),
    (re.compile(r"^/api/quality/"),                      "Backlog Quality — Other"),
    (re.compile(r"^/api/classify"),                      "Classify — Single Story"),
    (re.compile(r"^/api/verify"),                        "Verify — Bulk Upload"),
    (re.compile(r"^/api/disputes"),                      "Disputes"),
    (re.compile(r"^/api/aliases"),                       "Category Aliases"),
    (re.compile(r"^/api/merge"),                         "File Merger"),
    (re.compile(r"^/api/teams"),                         "Teams View"),
    (re.compile(r"^/api/epics"),                         "Epic Lineage"),
    (re.compile(r"^/api/dashboard"),                     "Dashboard"),
    (re.compile(r"^/api/analytics"),                     "Analytics — Other"),
    (re.compile(r"^/api/settings"),                      "Settings"),
    (re.compile(r"^/api/admin/usage"),                   "Admin — Usage Analytics"),
    # Page routes (top-level navigation hits)
    (re.compile(r"^/$"),                                 "Page — Home"),
    (re.compile(r"^/classify$"),                         "Page — Classify"),
    (re.compile(r"^/history$"),                          "Page — Analytics / Backlog Quality"),
    (re.compile(r"^/dashboard$"),                        "Page — Dashboard"),
    (re.compile(r"^/teams$"),                            "Page — Teams"),
    (re.compile(r"^/lineage$"),                          "Page — Epic Lineage"),
    (re.compile(r"^/disputes$"),                         "Page — Disputes"),
    (re.compile(r"^/merge$"),                            "Page — File Merger"),
    (re.compile(r"^/aliases$"),                          "Page — Category Aliases"),
    (re.compile(r"^/quality-domains$"),                  "Page — Domain Editor"),
    (re.compile(r"^/waf-reference$"),                    "Page — WAF Reference"),
    (re.compile(r"^/admin/usage$"),                      "Page — Usage Analytics"),
    (re.compile(r"^/settings$"),                         "Page — Settings"),
]

# Routes we DO NOT log — too noisy or not user-meaningful.
_SKIP_RULES = [
    re.compile(r"^/api/status$"),       # status pings, polled constantly
    re.compile(r"^/static/"),           # CSS/JS asset fetches
    re.compile(r"^/favicon"),
    re.compile(r"^/api/quality/job/"),  # progress polling — would dominate the data
]


def _classify_feature(path: str) -> str:
    for pat, name in _FEATURE_RULES:
        if pat.match(path):
            return name
    return "Other"


def _should_skip(path: str) -> bool:
    for pat in _SKIP_RULES:
        if pat.match(path):
            return True
    return False


# ── Pricing model — Anthropic Claude Sonnet/Opus per-million-token rates ────
# Source: anthropic.com/pricing as of May 2026. Update when pricing changes.
# Caller passes the model id; we look up rates here.

_MODEL_PRICING = {
    # Sonnet (default for most calls)
    "claude-sonnet-4-20250514":              {"in": 3.00,  "out": 15.00},
    "claude-3-5-sonnet-20241022":            {"in": 3.00,  "out": 15.00},
    "claude-3-5-sonnet-20240620":            {"in": 3.00,  "out": 15.00},
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {"in": 3.00, "out": 15.00},
    # Opus
    "claude-opus-4-20250514":                {"in": 15.00, "out": 75.00},
    "claude-3-opus-20240229":                {"in": 15.00, "out": 75.00},
    # Haiku
    "claude-haiku-4-20250514":               {"in": 0.80,  "out": 4.00},
    "claude-3-5-haiku-20241022":             {"in": 0.80,  "out": 4.00},
}

_DEFAULT_PRICING = {"in": 3.00, "out": 15.00}  # assume Sonnet if unknown


def _estimate_cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    p = _MODEL_PRICING.get(model or "", _DEFAULT_PRICING)
    return round((in_tok * p["in"] + out_tok * p["out"]) / 1_000_000.0, 6)


# ── Flask middleware ────────────────────────────────────────────────────────

def install_usage_tracking(app):
    """Register before/after_request handlers that log every request."""

    @app.before_request
    def _usage_before():
        g._usage_t0 = time.time()
        # Stable per-browser session id so we can count unique sessions
        # without identifying users. Stored in Flask's session cookie.
        try:
            sid = session.get("_usage_sid")
            if not sid:
                sid = uuid.uuid4().hex[:16]
                session["_usage_sid"] = sid
            g._usage_sid = sid
        except Exception:
            g._usage_sid = ""

    @app.after_request
    def _usage_after(response):
        try:
            path = request.path or ""
            if _should_skip(path):
                return response
            elapsed_ms = int((time.time() - getattr(g, "_usage_t0", time.time())) * 1000)
            feature = _classify_feature(path)
            sid = getattr(g, "_usage_sid", "")
            # Use a fresh sqlite connection — avoid Flask request-context coupling.
            try:
                conn = sqlite3.connect(DB_PATH, timeout=2.0)
                conn.execute(
                    "INSERT INTO usage_events (ts, route, method, status, response_ms, feature, session_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (datetime.now().isoformat(), path, request.method,
                     response.status_code, elapsed_ms, feature, sid),
                )
                conn.commit()
                conn.close()
            except Exception:
                # Never fail a request because tracking failed.
                pass
        except Exception:
            pass
        return response


# ── Token recorder (called from AI call sites) ──────────────────────────────

def record_token_use(model: str, input_tokens: int, output_tokens: int, route: str = None, feature: str = None):
    """Log an AI call's token usage. Safe to call outside a request context.

    Caller passes model + token counts; route/feature are auto-detected from
    the current request when omitted.
    """
    try:
        if route is None:
            try:
                route = request.path
            except Exception:
                route = ""
        if feature is None:
            feature = _classify_feature(route or "")
        cost = _estimate_cost_usd(model, int(input_tokens or 0), int(output_tokens or 0))
        conn = sqlite3.connect(DB_PATH, timeout=2.0)
        conn.execute(
            "INSERT INTO token_events (ts, route, feature, model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), route or "", feature or "Other",
             model or "", int(input_tokens or 0), int(output_tokens or 0), cost),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── Admin API endpoints ─────────────────────────────────────────────────────

def _resolve_window():
    """Resolve the requested time window.

    Query param `days`:
      - missing or 'all' → no time filter (all-time, the default)
      - integer N        → trailing N days

    Returns (cutoff_iso_or_None, window_label).
    """
    raw = request.args.get("days")
    if not raw or str(raw).strip().lower() in ("all", "0", "-1"):
        return None, "all"
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None, "all"
    days = max(1, min(365, days))
    return (datetime.now() - timedelta(days=days)).isoformat(), days


def _ts_filter(cutoff):
    """Return ('ts >= ?', [cutoff]) when cutoff is set, else ('1=1', [])."""
    if cutoff:
        return "ts >= ?", [cutoff]
    return "1=1", []


@admin_bp.route("/api/admin/usage/summary")
def admin_usage_summary():
    """Top-level KPIs for the dashboard header card."""
    cutoff, window = _resolve_window()
    db = get_db()
    where, ps = _ts_filter(cutoff)

    total_requests  = db.execute(f"SELECT COUNT(*) FROM usage_events WHERE {where}", ps).fetchone()[0]
    unique_features = db.execute(f"SELECT COUNT(DISTINCT feature) FROM usage_events WHERE {where}", ps).fetchone()[0]
    unique_sessions = db.execute(
        f"SELECT COUNT(DISTINCT session_id) FROM usage_events WHERE {where} AND session_id != ''", ps
    ).fetchone()[0]
    error_count = db.execute(
        f"SELECT COUNT(*) FROM usage_events WHERE {where} AND status >= 400", ps
    ).fetchone()[0]
    tokens = db.execute(
        f"SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(cost_usd),0) "
        f"FROM token_events WHERE {where}", ps,
    ).fetchone()
    earliest_row = db.execute(f"SELECT MIN(ts) FROM usage_events WHERE {where}", ps).fetchone()
    return jsonify({
        "window":          window,    # 'all' or integer days
        "since":           earliest_row[0] if earliest_row else None,
        "total_requests":  total_requests,
        "unique_features": unique_features,
        "unique_sessions": unique_sessions,
        "error_count":     error_count,
        "input_tokens":    tokens[0] or 0,
        "output_tokens":   tokens[1] or 0,
        "ai_cost_usd":     round(tokens[2] or 0.0, 4),
    })


@admin_bp.route("/api/admin/usage/features")
def admin_usage_features():
    """Per-feature usage table — sorted by hits descending.

    The frontend can display top N and bottom M however it wants.
    """
    cutoff, window = _resolve_window()
    db = get_db()
    where, ps = _ts_filter(cutoff)

    rows = db.execute(
        f"""SELECT feature,
                   COUNT(*) AS hits,
                   COUNT(DISTINCT session_id) AS sessions,
                   AVG(response_ms) AS avg_ms,
                   SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS errors,
                   MAX(ts) AS last_used
            FROM usage_events
            WHERE {where}
            GROUP BY feature
            ORDER BY hits DESC""",
        ps,
    ).fetchall()

    tok_rows = db.execute(
        f"""SELECT feature, SUM(cost_usd) AS cost,
                   SUM(input_tokens) AS in_tok, SUM(output_tokens) AS out_tok
            FROM token_events WHERE {where} GROUP BY feature""",
        ps,
    ).fetchall()
    tok_map = {r["feature"]: dict(r) for r in tok_rows}

    out = []
    for r in rows:
        t = tok_map.get(r["feature"], {})
        out.append({
            "feature":   r["feature"] or "Other",
            "hits":      r["hits"],
            "sessions":  r["sessions"],
            "avg_ms":    round(r["avg_ms"] or 0.0, 1),
            "errors":    r["errors"],
            "last_used": r["last_used"],
            "ai_cost_usd":   round(t.get("cost") or 0.0, 4),
            "input_tokens":  t.get("in_tok")  or 0,
            "output_tokens": t.get("out_tok") or 0,
        })
    return jsonify({"window": window, "features": out})


@admin_bp.route("/api/admin/usage/trend")
def admin_usage_trend():
    """Daily hit count for each feature in the window — feeds the trend chart."""
    cutoff, window = _resolve_window()
    db = get_db()
    where, ps = _ts_filter(cutoff)
    rows = db.execute(
        f"""SELECT substr(ts, 1, 10) AS day, feature, COUNT(*) AS hits
            FROM usage_events WHERE {where}
            GROUP BY day, feature ORDER BY day ASC""",
        ps,
    ).fetchall()
    return jsonify({
        "window": window,
        "points": [
            {"day": r["day"], "feature": r["feature"] or "Other", "hits": r["hits"]}
            for r in rows
        ],
    })


@admin_bp.route("/api/admin/usage/tokens-trend")
def admin_usage_tokens_trend():
    """Daily token cost trend — feeds the spend chart."""
    cutoff, window = _resolve_window()
    db = get_db()
    where, ps = _ts_filter(cutoff)
    rows = db.execute(
        f"""SELECT substr(ts, 1, 10) AS day,
                   SUM(input_tokens)  AS in_tok,
                   SUM(output_tokens) AS out_tok,
                   SUM(cost_usd)      AS cost
            FROM token_events WHERE {where}
            GROUP BY day ORDER BY day ASC""",
        ps,
    ).fetchall()
    return jsonify({
        "window": window,
        "points": [
            {
                "day": r["day"],
                "input_tokens":  r["in_tok"]  or 0,
                "output_tokens": r["out_tok"] or 0,
                "cost_usd":      round(r["cost"] or 0.0, 4),
            }
            for r in rows
        ],
    })


@admin_bp.route("/api/admin/usage/feature/<path:feature>")
def admin_usage_feature_detail(feature):
    """Drill-down for a single feature: daily series, raw routes, slowest, errors."""
    cutoff, window = _resolve_window()
    db = get_db()
    where, ps = _ts_filter(cutoff)
    daily = db.execute(
        f"""SELECT substr(ts, 1, 10) AS day, COUNT(*) AS hits,
                   AVG(response_ms) AS avg_ms,
                   SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS errors
            FROM usage_events WHERE {where} AND feature = ?
            GROUP BY day ORDER BY day ASC""",
        ps + [feature],
    ).fetchall()
    # Raw routes — critical for the 'Other' bucket so users can see exactly
    # which paths are landing there and what to add to the feature catalog.
    routes = db.execute(
        f"""SELECT route, method, COUNT(*) AS hits,
                   AVG(response_ms) AS avg_ms,
                   SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS errors,
                   MAX(ts) AS last_used
            FROM usage_events WHERE {where} AND feature = ?
            GROUP BY route, method ORDER BY hits DESC LIMIT 30""",
        ps + [feature],
    ).fetchall()
    slowest = db.execute(
        f"""SELECT route, method, status, response_ms, ts
            FROM usage_events WHERE {where} AND feature = ?
            ORDER BY response_ms DESC LIMIT 10""",
        ps + [feature],
    ).fetchall()
    errors = db.execute(
        f"""SELECT route, status, COUNT(*) AS cnt
            FROM usage_events WHERE {where} AND feature = ? AND status >= 400
            GROUP BY route, status ORDER BY cnt DESC""",
        ps + [feature],
    ).fetchall()
    tokens = db.execute(
        f"""SELECT COALESCE(SUM(input_tokens),0)  AS in_tok,
                   COALESCE(SUM(output_tokens),0) AS out_tok,
                   COALESCE(SUM(cost_usd),0)      AS cost
            FROM token_events WHERE {where} AND feature = ?""",
        ps + [feature],
    ).fetchone()
    return jsonify({
        "feature": feature,
        "window":  window,
        "daily":   [dict(r) for r in daily],
        "routes":  [{"route": r["route"], "method": r["method"], "hits": r["hits"],
                     "avg_ms": round(r["avg_ms"] or 0.0, 1), "errors": r["errors"],
                     "last_used": r["last_used"]} for r in routes],
        "slowest": [dict(r) for r in slowest],
        "errors":  [dict(r) for r in errors],
        "tokens":  {"input": tokens[0] or 0, "output": tokens[1] or 0,
                    "cost_usd": round(tokens[2] or 0.0, 4)},
    })
