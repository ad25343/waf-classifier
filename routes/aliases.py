"""
WAF Classifier — WAF category alias management.
Lets users add custom shorthand→canonical mappings via the UI so the
matcher recognises team-specific variants without redeploying code.
"""

from datetime import datetime

from flask import Blueprint, request, jsonify

from database import get_db
from state import waf_store, DEFAULT_WAF_CATEGORIES

aliases_bp = Blueprint("aliases_bp", __name__)


def _canonical_categories():
    """Active WAF categories (uploaded definitions, falling back to defaults)."""
    cats = waf_store.get("categories") or DEFAULT_WAF_CATEGORIES
    return [str(c).strip() for c in cats if c and str(c).strip().lower() != "nan"]


def _bust_cache():
    """Invalidate the in-memory alias cache so the next normalize call
    re-reads from the DB. Imported lazily to avoid an import cycle."""
    try:
        from waf_core import invalidate_alias_cache
        invalidate_alias_cache()
    except Exception:
        pass


# ── GET /api/aliases ─────────────────────────────────────────────────

@aliases_bp.route("/api/aliases", methods=["GET"])
def list_aliases():
    db = get_db()
    rows = db.execute(
        "SELECT id, alias, canonical, source, created_at, created_by "
        "FROM waf_aliases ORDER BY canonical, alias"
    ).fetchall()
    return jsonify({
        "aliases": [dict(r) for r in rows],
        "categories": _canonical_categories(),
    })


# ── POST /api/aliases ────────────────────────────────────────────────

@aliases_bp.route("/api/aliases", methods=["POST"])
def create_alias():
    data = request.json or {}
    alias = (data.get("alias") or "").strip()
    canonical = (data.get("canonical") or "").strip()
    created_by = (data.get("created_by") or "").strip()

    if not alias:
        return jsonify({"error": "Alias is required"}), 400
    if not canonical:
        return jsonify({"error": "Canonical category is required"}), 400

    cats = _canonical_categories()
    # Optional sanity check — don't block if WAF definitions aren't loaded yet,
    # but warn if the canonical isn't in the active list so users don't typo.
    canonical_known = any(c.lower() == canonical.lower() for c in cats)
    if cats and not canonical_known:
        return jsonify({
            "error": f"Canonical category '{canonical}' is not in the active WAF list. "
                     f"Pick one of the existing categories or upload an updated WAF file first."
        }), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO waf_aliases (alias, canonical, source, created_at, created_by) "
            "VALUES (?, ?, 'user', ?, ?)",
            (alias, canonical, datetime.now().isoformat(), created_by),
        )
        db.commit()
    except Exception as e:
        # SQLite IntegrityError on UNIQUE alias constraint
        if "UNIQUE" in str(e):
            return jsonify({"error": f"Alias '{alias}' already exists"}), 409
        return jsonify({"error": "Failed to create alias"}), 500

    _bust_cache()
    return jsonify({"success": True, "id": cur.lastrowid}), 201


# ── DELETE /api/aliases/<id> ─────────────────────────────────────────

@aliases_bp.route("/api/aliases/<int:alias_id>", methods=["DELETE"])
def delete_alias(alias_id):
    db = get_db()
    result = db.execute("DELETE FROM waf_aliases WHERE id=?", (alias_id,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Alias not found"}), 404
    _bust_cache()
    return jsonify({"success": True})
