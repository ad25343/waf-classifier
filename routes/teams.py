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
               was_mismatch, approved, confidence,
               COALESCE(team_of_teams, '') as team_of_teams
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
        "team_of_teams": defaultdict(int),   # ToT → story count
    })

    # Cross-team tracking
    epic_teams = defaultdict(set)
    # Team of Teams → teams mapping
    tot_teams = defaultdict(set)

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
        tot = row["team_of_teams"]
        if tot:
            t["team_of_teams"][tot] += 1
            tot_teams[tot].add(team)

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

        # Determine primary Team of Teams (most common value for this team)
        primary_tot = max(t["team_of_teams"], key=t["team_of_teams"].get) if t["team_of_teams"] else ""

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
            "team_of_teams": primary_tot,
        })

    # Cross-team data
    teams_by_epic = {epic: sorted(tms) for epic, tms in epic_teams.items()}
    epics_by_team = {name: sorted(t["epics"]) for name, t in team_data.items()}

    # Totals
    avg_mismatch = round(sum(total_mismatch_rates) / len(total_mismatch_rates), 1) if total_mismatch_rates else 0
    most_active = max(teams, key=lambda x: x["total_stories"])["name"] if teams else ""

    # Build Team of Teams list sorted by name
    tot_list = sorted([
        {"name": tot, "teams": sorted(tms), "team_count": len(tms)}
        for tot, tms in tot_teams.items()
    ], key=lambda x: x["name"])

    return jsonify({
        "teams": teams,
        "team_of_teams": tot_list,
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
    """Return stories for a single team, grouped by epic and feature."""
    team = request.args.get("team", "")
    if not team:
        return jsonify({"error": "team parameter is required"}), 400

    upload_id = request.args.get("upload_id")
    db = get_db()
    query = """SELECT id, story_title, story_description, waf_category, waf_color,
                  run_change, confidence, was_mismatch, epic, parent_feature,
                  timestamp, story_id, feature_id, epic_id, pi_number, waf_reasoning
           FROM classifications
           WHERE team = ?"""
    params = [team]
    if upload_id:
        query += " AND upload_id = ?"
        params.append(upload_id)
    query += " ORDER BY epic, parent_feature, timestamp DESC"
    rows = db.execute(query, params).fetchall()

    # Group stories by epic -> feature
    epic_map = defaultdict(lambda: {
        "story_count": 0,
        "mismatches": 0,
        "features": defaultdict(lambda: {"stories": [], "story_count": 0}),
    })

    total_stories = 0
    categories = defaultdict(int)
    dominant_cat = ""

    for r in rows:
        epic_name = r["epic"] or "(No Epic)"
        feature_name = r["parent_feature"] or "(No Feature)"
        ep = epic_map[epic_name]
        ft = ep["features"][feature_name]

        story = {
            "id": r["id"],
            "title": r["story_title"],
            "description": r["story_description"] or "",
            "waf_category": r["waf_category"],
            "waf_color": r["waf_color"] or "",
            "run_change": r["run_change"] or "",
            "confidence": r["confidence"] or "",
            "was_mismatch": bool(r["was_mismatch"]),
            "epic": r["epic"] or "",
            "parent_feature": r["parent_feature"] or "",
            "timestamp": r["timestamp"],
            "story_id": r["story_id"] or "",
            "feature_id": r["feature_id"] or "",
            "epic_id": r["epic_id"] or "",
            "pi_number": r["pi_number"] or "",
            "waf_reasoning": r["waf_reasoning"] or "",
        }

        ft["stories"].append(story)
        ft["story_count"] += 1
        ep["story_count"] += 1
        if r["was_mismatch"]:
            ep["mismatches"] += 1
        total_stories += 1
        if r["waf_category"]:
            categories[r["waf_category"]] += 1

    if categories:
        dominant_cat = max(categories, key=categories.get)

    # Build structured response
    epics = []
    for epic_name in sorted(epic_map.keys()):
        ep = epic_map[epic_name]
        features = []
        for feat_name in sorted(ep["features"].keys()):
            ft = ep["features"][feat_name]
            features.append({
                "name": feat_name,
                "story_count": ft["story_count"],
                "stories": ft["stories"],
            })
        epics.append({
            "name": epic_name,
            "story_count": ep["story_count"],
            "mismatches": ep["mismatches"],
            "features": features,
        })

    mismatch_count = sum(e["mismatches"] for e in epics)
    mismatch_rate = round((mismatch_count / total_stories) * 100, 1) if total_stories else 0

    return jsonify({
        "team": team,
        "total_stories": total_stories,
        "epic_count": len(epics),
        "mismatch_count": mismatch_count,
        "mismatch_rate": mismatch_rate,
        "dominant_category": dominant_cat,
        "epics": epics,
    })


@teams_bp.route("/api/teams/by-epic")
def teams_by_epic():
    """Return all teams working on a specific epic."""
    epic = request.args.get("epic", "")
    if not epic:
        return jsonify({"error": "epic parameter is required"}), 400

    upload_id = request.args.get("upload_id")
    db = get_db()
    query = """SELECT id, story_title, story_description, waf_category, waf_color,
                  run_change, confidence, was_mismatch, team, parent_feature,
                  timestamp, waf_reasoning
           FROM classifications
           WHERE epic = ?"""
    params = [epic]
    if upload_id:
        query += " AND upload_id = ?"
        params.append(upload_id)
    query += " ORDER BY team, timestamp DESC"
    rows = db.execute(query, params).fetchall()

    team_map = defaultdict(lambda: {
        "stories": [],
        "story_count": 0,
        "mismatches": 0,
        "categories": defaultdict(int),
    })

    total_stories = 0

    for r in rows:
        team_name = r["team"] or "(No Team)"
        tm = team_map[team_name]

        story = {
            "id": r["id"],
            "title": r["story_title"],
            "description": r["story_description"] or "",
            "waf_category": r["waf_category"],
            "waf_color": r["waf_color"] or "",
            "run_change": r["run_change"] or "",
            "confidence": r["confidence"] or "",
            "was_mismatch": bool(r["was_mismatch"]),
            "parent_feature": r["parent_feature"] or "",
            "timestamp": r["timestamp"],
            "waf_reasoning": r["waf_reasoning"] or "",
        }

        tm["stories"].append(story)
        tm["story_count"] += 1
        if r["was_mismatch"]:
            tm["mismatches"] += 1
        if r["waf_category"]:
            tm["categories"][r["waf_category"]] += 1
        total_stories += 1

    # Compute category distribution across all teams
    all_categories = defaultdict(int)
    teams = []
    for name in sorted(team_map.keys()):
        tm = team_map[name]
        mismatch_rate = round((tm["mismatches"] / tm["story_count"]) * 100, 1) if tm["story_count"] else 0
        cats = dict(tm["categories"])
        for c, v in cats.items():
            all_categories[c] += v
        teams.append({
            "name": name,
            "story_count": tm["story_count"],
            "mismatches": tm["mismatches"],
            "mismatch_rate": mismatch_rate,
            "categories": cats,
            "stories": tm["stories"],
        })

    return jsonify({
        "epic": epic,
        "total_stories": total_stories,
        "team_count": len(teams),
        "category_distribution": dict(all_categories),
        "teams": teams,
    })


@teams_bp.route("/api/teams/epics-list")
def epics_list():
    """Return list of all epics with team and story counts."""
    upload_id = request.args.get("upload_id")
    db = get_db()
    query = """SELECT epic, team, COUNT(*) as cnt
           FROM classifications
           WHERE epic != '' AND team != '' AND team != 'default'"""
    params = []
    if upload_id:
        query += " AND upload_id = ?"
        params.append(upload_id)
    query += " GROUP BY epic, team"
    rows = db.execute(query, params).fetchall()

    epic_map = defaultdict(lambda: {"teams": set(), "story_count": 0})
    for r in rows:
        ep = epic_map[r["epic"]]
        ep["teams"].add(r["team"])
        ep["story_count"] += r["cnt"]

    epics = []
    for name in sorted(epic_map.keys()):
        ep = epic_map[name]
        epics.append({
            "name": name,
            "team_count": len(ep["teams"]),
            "story_count": ep["story_count"],
        })

    return jsonify({"epics": epics})
