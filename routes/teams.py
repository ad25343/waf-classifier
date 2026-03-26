"""
WAF Classifier — Teams API routes.
Provides team-level WAF analytics, epic assignments, and cross-team reporting.
"""

from collections import defaultdict
from flask import Blueprint, request, jsonify
from database import get_db

teams_bp = Blueprint("teams_bp", __name__)


@teams_bp.route("/api/teams/summary")
def teams_summary():
    """Return aggregated team-level analytics."""
    db = get_db()
    upload_id = request.args.get("upload_id")

    query = """
        SELECT team, epic, waf_category, waf_color, run_change,
               was_mismatch, approved, confidence
        FROM classifications
        WHERE team != '' AND team != 'default'
    """
    params = []
    if upload_id:
        query += " AND upload_id = ?"
        params.append(upload_id)

    rows = db.execute(query, params).fetchall()

    # Aggregate per team
    team_data = defaultdict(lambda: {
        "stories": 0,
        "epics": set(),
        "mismatches": 0,
        "approved": 0,
        "categories": defaultdict(int),
        "colors": defaultdict(int),
        "run_change": defaultdict(int),
        "confidence": defaultdict(int),
    })

    # Cross-team tracking
    epic_teams = defaultdict(set)

    for row in rows:
        team = row["team"]
        t = team_data[team]
        t["stories"] += 1
        if row["epic"]:
            t["epics"].add(row["epic"])
            epic_teams[row["epic"]].add(team)
        if row["was_mismatch"]:
            t["mismatches"] += 1
        if row["approved"]:
            t["approved"] += 1
        if row["waf_category"]:
            t["categories"][row["waf_category"]] += 1
        if row["waf_color"]:
            t["colors"][row["waf_color"]] += 1
        if row["run_change"]:
            t["run_change"][row["run_change"]] += 1
        if row["confidence"]:
            t["confidence"][row["confidence"].upper()] += 1

    # Build response
    teams = []
    total_stories = 0
    total_mismatch_rates = []

    for name, t in sorted(team_data.items()):
        epic_list = sorted(t["epics"])
        mismatch_rate = round((t["mismatches"] / t["stories"]) * 100, 1) if t["stories"] else 0
        total_stories += t["stories"]
        total_mismatch_rates.append(mismatch_rate)

        # Determine dominant category
        dominant_category = ""
        if t["categories"]:
            dominant_category = max(t["categories"], key=t["categories"].get)

        teams.append({
            "name": name,
            "total_stories": t["stories"],
            "epics": epic_list,
            "epic_count": len(epic_list),
            "mismatches": t["mismatches"],
            "mismatch_rate": mismatch_rate,
            "approved": t["approved"],
            "categories": dict(t["categories"]),
            "colors": dict(t["colors"]),
            "run_change": dict(t["run_change"]),
            "dominant_category": dominant_category,
            "confidence_breakdown": dict(t["confidence"]),
        })

    # Cross-team data
    teams_by_epic = {epic: sorted(tms) for epic, tms in epic_teams.items()}
    epics_by_team = {name: sorted(t["epics"]) for name, t in team_data.items()}

    # Totals
    avg_mismatch = round(sum(total_mismatch_rates) / len(total_mismatch_rates), 1) if total_mismatch_rates else 0
    most_active = max(teams, key=lambda x: x["total_stories"])["name"] if teams else ""

    return jsonify({
        "teams": teams,
        "cross_team": {
            "teams_by_epic": teams_by_epic,
            "epics_by_team": epics_by_team,
        },
        "totals": {
            "team_count": len(teams),
            "total_stories": total_stories,
            "avg_mismatch_rate": avg_mismatch,
            "most_active_team": most_active,
        },
    })


@teams_bp.route("/api/teams/detail")
def teams_detail():
    """Return full story list for a single team."""
    team = request.args.get("team", "")
    if not team:
        return jsonify({"error": "team parameter is required"}), 400

    db = get_db()
    rows = db.execute(
        """SELECT id, story_title, story_description, waf_category, waf_color,
                  run_change, confidence, was_mismatch, epic, timestamp
           FROM classifications
           WHERE team = ?
           ORDER BY timestamp DESC""",
        (team,),
    ).fetchall()

    stories = []
    for r in rows:
        stories.append({
            "id": r["id"],
            "title": r["story_title"],
            "description": r["story_description"] or "",
            "waf_category": r["waf_category"],
            "waf_color": r["waf_color"] or "",
            "run_change": r["run_change"] or "",
            "confidence": r["confidence"] or "",
            "was_mismatch": bool(r["was_mismatch"]),
            "epic": r["epic"] or "",
            "timestamp": r["timestamp"],
        })

    return jsonify({"team": team, "stories": stories})
