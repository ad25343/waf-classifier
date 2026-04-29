"""
WAF Classifier — Classification Disputes routes.
Allows users to flag disagreements with AI classifications and
reviewers to resolve them (dismiss, accept into GT, or flag for WAF review).
"""

import math
from datetime import datetime

from flask import Blueprint, request, jsonify

from database import get_db, save_classification

disputes_bp = Blueprint("disputes_bp", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row)


# ── POST /api/disputes — create a dispute ─────────────────────────────────────

@disputes_bp.route("/api/disputes", methods=["POST"])
def create_dispute():
    data = request.json or {}

    story_title = data.get("story_title", "").strip()
    if not story_title:
        return jsonify({"error": "story_title is required"}), 400

    now = datetime.now().isoformat()

    db = get_db()
    cursor = db.execute(
        """INSERT INTO disputes
           (created_at, story_title, story_description,
            ai_category, ai_color, ai_confidence, ai_reasoning,
            user_comment, suggested_category,
            status, team, epic, story_id, pi_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            now,
            story_title,
            data.get("story_description", ""),
            data.get("ai_category", ""),
            data.get("ai_color", ""),
            data.get("ai_confidence", ""),
            data.get("ai_reasoning", ""),
            data.get("user_comment", ""),
            data.get("suggested_category", ""),
            data.get("team", ""),
            data.get("epic", ""),
            data.get("story_id", ""),
            data.get("pi_number", ""),
        ),
    )
    db.commit()
    return jsonify({"success": True, "id": cursor.lastrowid}), 201


# ── GET /api/disputes — list disputes ────────────────────────────────────────

@disputes_bp.route("/api/disputes", methods=["GET"])
def list_disputes():
    status_filter = request.args.get("status", "pending")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(200, request.args.get("per_page", 25, type=int)))

    db = get_db()

    # Count totals per status for the counts badge
    count_rows = db.execute(
        "SELECT status, COUNT(*) as cnt FROM disputes GROUP BY status"
    ).fetchall()
    counts = {"pending": 0, "dismissed": 0, "accepted": 0, "waf_flagged": 0}
    for r in count_rows:
        s = r["status"]
        if s in counts:
            counts[s] = r["cnt"]

    # Build WHERE clause
    if status_filter == "all":
        where = "1=1"
        params = []
    else:
        where = "status = ?"
        params = [status_filter]

    total = db.execute(
        f"SELECT COUNT(*) FROM disputes WHERE {where}", params
    ).fetchone()[0]

    total_pages = max(1, math.ceil(total / per_page))
    offset = (page - 1) * per_page

    # Pending first, then by created_at DESC
    rows = db.execute(
        f"""SELECT * FROM disputes
            WHERE {where}
            ORDER BY
                CASE WHEN status='pending' THEN 0 ELSE 1 END ASC,
                created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    return jsonify({
        "disputes": [_row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "counts": counts,
    })


# ── POST /api/disputes/<id>/resolve — resolve a dispute ──────────────────────

@disputes_bp.route("/api/disputes/<int:dispute_id>/resolve", methods=["POST"])
def resolve_dispute(dispute_id):
    data = request.json or {}
    action = data.get("action", "")

    valid_actions = {"dismiss", "accept_gt", "flag_waf"}
    if action not in valid_actions:
        return jsonify({"error": f"action must be one of: {', '.join(sorted(valid_actions))}"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()
    if not row:
        return jsonify({"error": "Dispute not found"}), 404

    status_map = {
        "dismiss": "dismissed",
        "accept_gt": "accepted",
        "flag_waf": "flagged_waf",
    }
    new_status = status_map[action]

    gt_updated = 1 if action == "accept_gt" else 0
    waf_flagged = 1 if action == "flag_waf" else 0
    reviewed_at = datetime.now().isoformat()
    reviewer_notes = data.get("reviewer_notes", "")
    resolved_category = data.get("resolved_category", "")
    resolved_color = data.get("resolved_color", "")

    db.execute(
        """UPDATE disputes
           SET status=?, reviewed_at=?, reviewer_notes=?,
               resolved_category=?, resolved_color=?,
               gt_updated=?, waf_flagged=?
           WHERE id=?""",
        (new_status, reviewed_at, reviewer_notes,
         resolved_category, resolved_color,
         gt_updated, waf_flagged, dispute_id),
    )
    db.commit()

    # If accepting into GT, save the corrected classification
    if action == "accept_gt" and resolved_category:
        dispute = _row_to_dict(row)
        save_classification(
            title=dispute.get("story_title", ""),
            description=dispute.get("story_description", ""),
            category=resolved_category,
            team_of_teams="",
            color=resolved_color,
            run_change="",
            confidence=dispute.get("ai_confidence", ""),
            was_mismatch=True,
            original_tag=dispute.get("ai_category", ""),
            approved=True,
            team=dispute.get("team", "default") or "default",
            epic=dispute.get("epic", ""),
            parent_feature="",
            story_id=dispute.get("story_id", ""),
            feature_id="",
            epic_id="",
            story_points="",
            original_color=dispute.get("ai_color", ""),
            waf_reasoning=dispute.get("ai_reasoning", ""),
            pi_number=dispute.get("pi_number", ""),
        )

    return jsonify({"success": True})


# ── DELETE /api/disputes/<id> — hard delete a dispute ────────────────────────

@disputes_bp.route("/api/disputes/<int:dispute_id>", methods=["DELETE"])
def delete_dispute(dispute_id):
    db = get_db()
    result = db.execute("DELETE FROM disputes WHERE id=?", (dispute_id,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Dispute not found"}), 404
    return jsonify({"success": True})
