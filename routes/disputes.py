"""
WAF Classifier — Classification Disputes routes.
Allows users to flag disagreements with AI classifications and
reviewers to resolve them (dismiss, accept into GT, or flag for WAF review).
"""

import json
import math
import re
from datetime import datetime

from flask import Blueprint, request, jsonify

from config import AI_MODEL
from database import get_db, save_classification
# Reuse the AI client + token logger already used by quality scoring.
from routes.quality import _get_client, _log_tokens_safe

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

    # 'reopen' rolls a previously-resolved dispute back to pending and
    # clears all resolution fields. The three accept/dismiss/flag actions
    # are idempotent — calling any of them on an already-resolved dispute
    # overwrites the previous resolution cleanly.
    valid_actions = {"dismiss", "accept_gt", "flag_waf", "reopen"}
    if action not in valid_actions:
        return jsonify({"error": f"action must be one of: {', '.join(sorted(valid_actions))}"}), 400

    db = get_db()
    row = db.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()
    if not row:
        return jsonify({"error": "Dispute not found"}), 404

    status_map = {
        "dismiss":   "dismissed",
        "accept_gt": "accepted",
        "flag_waf":  "flagged_waf",
        "reopen":    "pending",
    }
    new_status = status_map[action]

    gt_updated = 1 if action == "accept_gt" else 0
    waf_flagged = 1 if action == "flag_waf" else 0
    # reopen clears reviewed_at + notes + resolved_*; resolutions stamp them.
    if action == "reopen":
        reviewed_at = None
        reviewer_notes = ""
        resolved_category = ""
        resolved_color = ""
    else:
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

    # If accepting into GT, save the corrected classification.
    # Reviewer can override the dispute's original title + description
    # (via the editable fields / Enhance button on the modal) so we
    # only inject polished, GT-quality text into the training set.
    if action == "accept_gt" and resolved_category:
        dispute = _row_to_dict(row)
        gt_title       = (data.get("resolved_title")       or dispute.get("story_title",       "")).strip()
        gt_description = (data.get("resolved_description") or dispute.get("story_description", "")).strip()
        save_classification(
            title=gt_title,
            description=gt_description,
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


# ── POST /api/disputes/<id>/enhance — AI polish title + description ─────────

@disputes_bp.route("/api/disputes/<int:dispute_id>/enhance", methods=["POST"])
def enhance_dispute(dispute_id):
    """Rewrite a dispute's title + description into clean GT-quality text.

    The accept_gt flow writes a row into classifications which the AI then
    uses to calibrate future classifications — so the GT set must stay
    clean. This endpoint takes the dispute's original story content +
    the resolved category and asks the AI to produce a polished version
    that preserves intent but removes typos, ticket-number noise,
    markdown artifacts, and ambiguous phrasing.

    Body (all optional — falls back to stored dispute fields):
      title              str  reviewer's current draft title
      description        str  reviewer's current draft description
      resolved_category  str  target WAF category for calibration
      resolved_color     str  target color (informational only)

    Returns:
      {title: str, description: str, changes: str}
    """
    db = get_db()
    row = db.execute("SELECT * FROM disputes WHERE id=?", (dispute_id,)).fetchone()
    if not row:
        return jsonify({"error": "Dispute not found"}), 404

    data = request.json or {}
    dispute = _row_to_dict(row)
    title = (data.get("title")             or dispute.get("story_title",       "")).strip()
    desc  = (data.get("description")       or dispute.get("story_description", "")).strip()
    cat   = (data.get("resolved_category") or dispute.get("suggested_category", "")).strip()
    color = (data.get("resolved_color")    or "").strip()
    user_comment = dispute.get("user_comment", "")

    if not title and not desc:
        return jsonify({"error": "Nothing to enhance — both title and description are empty"}), 400

    prompt = f"""You are polishing a JIRA story that will be inserted into the WAF Classifier's
Ground Truth training set. GT examples calibrate every future AI classification,
so they must be clear, well-structured, and unambiguously represent their
category. Your job is to clean the story without changing its meaning.

Target WAF category: {cat or '(not specified)'}
Target color: {color or '(not specified)'}

Reviewer's reasoning for this classification:
{user_comment or '(none provided)'}

ORIGINAL TITLE:
{title or '(empty)'}

ORIGINAL DESCRIPTION:
{desc or '(empty)'}

Rules:
- Preserve the original intent. Do not invent facts (system names, dates,
  metrics, user roles) that weren't in the input.
- Remove typos, JIRA noise (ticket numbers, markdown artifacts, status
  stamps like "[DONE]" or "@mention"), and ambiguous phrasing.
- Keep the title concise (under 100 chars) and the description focused
  (2–4 sentences is typical for a GT example).
- If the original is already clean, return it essentially unchanged
  and say so in `changes`.

Return a JSON object with exactly these keys, nothing else:
{{
  "title":       "polished title",
  "description": "polished description",
  "changes":     "1-2 sentence summary of what you changed and why (or 'no changes needed')"
}}"""

    try:
        client = _get_client()
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        _log_tokens_safe(resp, AI_MODEL, route="/api/disputes/enhance")
        raw = resp.content[0].text.strip()
        # Strip code fences if the model wrapped the JSON in them
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return jsonify({"error": "AI response was not valid JSON", "raw": raw[:400]}), 502
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError as je:
            return jsonify({"error": f"AI response parse failed: {je}", "raw": raw[:400]}), 502
        return jsonify({
            "title":       (out.get("title")       or title).strip(),
            "description": (out.get("description") or desc).strip(),
            "changes":     (out.get("changes")     or "").strip(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── DELETE /api/disputes/<id> — hard delete a dispute ────────────────────────

@disputes_bp.route("/api/disputes/<int:dispute_id>", methods=["DELETE"])
def delete_dispute(dispute_id):
    db = get_db()
    result = db.execute("DELETE FROM disputes WHERE id=?", (dispute_id,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Dispute not found"}), 404
    return jsonify({"success": True})
