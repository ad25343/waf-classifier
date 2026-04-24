"""
Epic lineage routes: list epics, summary, uploads, assign, autocomplete.
"""

from collections import defaultdict

from flask import Blueprint, request, jsonify

from database import get_db

lineage_bp = Blueprint("lineage_bp", __name__)


@lineage_bp.route("/api/epics", methods=["GET"])
def list_epics():
    """List all unique epics with story counts. Optional ?upload_id= filter."""
    db = get_db()
    upload_id = request.args.get("upload_id", "")
    where = "epic != '' AND epic IS NOT NULL"
    params = []
    if upload_id:
        where += " AND upload_id = ?"
        params.append(int(upload_id))

    rows = db.execute(
        f"""SELECT epic, COUNT(*) as cnt,
                  SUM(CASE WHEN was_mismatch=1 THEN 1 ELSE 0 END) as mismatches,
                  SUM(CASE WHEN approved=1 THEN 1 ELSE 0 END) as approved
           FROM classifications
           WHERE {where}
           GROUP BY epic ORDER BY cnt DESC""",
        params
    ).fetchall()

    return jsonify({
        "epics": [{"name": r["epic"], "story_count": r["cnt"],
                    "mismatches": r["mismatches"], "approved": r["approved"]}
                   for r in rows]
    })


@lineage_bp.route("/api/epics/summary", methods=["GET"])
def epic_summary():
    """Get dashboard-style summary for all epics or a specific epic. Optional ?upload_id= filter."""
    db = get_db()
    epic_filter = request.args.get("epic", "")
    upload_id = request.args.get("upload_id", "")

    where = "epic != '' AND epic IS NOT NULL"
    params = []
    if epic_filter:
        where += " AND epic = ?"
        params.append(epic_filter)
    if upload_id:
        where += " AND upload_id = ?"
        params.append(int(upload_id))

    rows = db.execute(
        f"""SELECT id, timestamp, story_title, story_description, waf_category,
                   waf_subcategory, waf_color, run_change, confidence,
                   was_mismatch, original_tag, approved, team, epic, parent_feature,
                   story_id, feature_id, epic_id, story_points, original_color, waf_reasoning, pi_number
            FROM classifications WHERE {where} ORDER BY epic, timestamp DESC""",
        params
    ).fetchall()

    if not rows:
        return jsonify({"epics": []})

    epics = defaultdict(list)
    for r in rows:
        epics[r["epic"]].append(r)

    result = []
    for epic_name, stories in epics.items():
        total = len(stories)
        approved = sum(1 for s in stories if s["approved"])
        mismatches = sum(1 for s in stories if s["was_mismatch"])

        def _pts(s):
            try:
                v = str(s["story_points"] or "").strip()
                return float(v) if v else 0
            except (ValueError, TypeError):
                return 0

        total_points = sum(_pts(s) for s in stories)

        cat_counts = {}
        submitted_cat_counts = {}
        color_counts = {}
        rc_counts = {}
        feature_map = defaultdict(list)  # parent_feature -> stories

        for s in stories:
            cat = s["waf_category"] or "Unknown"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
            sub_cat = s["original_tag"] or ""
            if sub_cat:
                submitted_cat_counts[sub_cat] = submitted_cat_counts.get(sub_cat, 0) + 1
            if s["waf_color"]:
                color_counts[s["waf_color"]] = color_counts.get(s["waf_color"], 0) + 1
            if s["run_change"]:
                rc_counts[s["run_change"]] = rc_counts.get(s["run_change"], 0) + 1
            feat = s["parent_feature"] or "(Direct)"
            feature_map[feat].append({
                "id": s["id"],
                "title": s["story_title"],
                "description": s["story_description"],
                "category": s["waf_category"],
                "original_tag": s["original_tag"],
                "color": s["waf_color"],
                "run_change": s["run_change"],
                "confidence": s["confidence"],
                "mismatch": bool(s["was_mismatch"]),
                "approved": bool(s["approved"]),
                "team": s["team"],
                "story_id": s["story_id"] or "",
                "feature_id": s["feature_id"] or "",
                "epic_id": s["epic_id"] or "",
                "epic": s["epic"] or "",
                "story_points": s["story_points"] or "",
                "original_color": s["original_color"] or "",
                "waf_reasoning": s["waf_reasoning"] or "",
                "pi_number": s["pi_number"] or "",
            })

        # Build tree: epic -> features -> stories
        features = []
        for feat_name, feat_stories in feature_map.items():
            feat_cats = {}
            feat_pts = 0
            for fs in feat_stories:
                c = fs["category"] or "Unknown"
                feat_cats[c] = feat_cats.get(c, 0) + 1
                try:
                    feat_pts += float(fs["story_points"]) if fs["story_points"] else 0
                except (ValueError, TypeError):
                    pass
            features.append({
                "name": feat_name,
                "story_count": len(feat_stories),
                "total_points": feat_pts,
                "categories": feat_cats,
                "stories": feat_stories,
            })

        # ── Health metrics ──
        # Dominant color: the most frequent WAF color in this epic
        dominant_color = max(color_counts, key=color_counts.get) if color_counts else ""
        dominant_color_pct = round(color_counts.get(dominant_color, 0) / total * 100, 1) if total and dominant_color else 0
        # Color consistency: % of stories matching the dominant color (higher = more focused)
        color_consistency = dominant_color_pct
        # Category focus: % of stories in the top category
        dominant_cat = max(cat_counts, key=cat_counts.get) if cat_counts else ""
        dominant_cat_pct = round(cat_counts.get(dominant_cat, 0) / total * 100, 1) if total and dominant_cat else 0
        # Unique colors & categories
        unique_colors = len(color_counts)
        unique_categories = len(cat_counts)
        # Health score: 0-100 (higher = cleaner)
        # Penalize for: many colors, low dominant %, mismatches
        health = round(
            (dominant_color_pct * 0.4) +
            (dominant_cat_pct * 0.3) +
            ((100 - min(unique_colors * 15, 100)) * 0.2) +
            ((100 - round(mismatches / total * 100, 1) if total else 100) * 0.1)
        ) if total else 0
        health = max(0, min(100, health))

        # Flag: is this epic "mixed" (3+ colors or dominant < 60%)?
        is_mixed = unique_colors >= 3 or dominant_color_pct < 60

        # Teams involved
        team_set = set(s["team"] for s in stories if s["team"] and s["team"] != "default")

        result.append({
            "epic": epic_name,
            "total_stories": total,
            "total_points": total_points,
            "approved": approved,
            "mismatches": mismatches,
            "approval_rate": round(approved / total * 100, 1) if total else 0,
            "mismatch_rate": round(mismatches / total * 100, 1) if total else 0,
            "categories": cat_counts,
            "submitted_categories": submitted_cat_counts,
            "colors": color_counts,
            "run_change": rc_counts,
            "features": features,
            "health": health,
            "dominant_color": dominant_color,
            "dominant_color_pct": dominant_color_pct,
            "dominant_category": dominant_cat,
            "dominant_category_pct": dominant_cat_pct,
            "color_consistency": color_consistency,
            "unique_colors": unique_colors,
            "unique_categories": unique_categories,
            "is_mixed": is_mixed,
            "teams": list(team_set),
        })

    return jsonify({"epics": result})


@lineage_bp.route("/api/epics/uploads", methods=["GET"])
def epic_uploads():
    """List uploads that contain epic data, for the lineage filter dropdown."""
    db = get_db()
    rows = db.execute(
        """SELECT DISTINCT c.upload_id, h.filename, h.uploaded_at, h.imported_count
           FROM classifications c
           JOIN upload_history h ON h.id = c.upload_id
           WHERE c.epic != '' AND c.epic IS NOT NULL AND c.upload_id IS NOT NULL
           GROUP BY c.upload_id
           ORDER BY h.uploaded_at DESC"""
    ).fetchall()
    return jsonify({
        "uploads": [{"upload_id": r["upload_id"], "filename": r["filename"],
                      "uploaded_at": r["uploaded_at"], "imported_count": r["imported_count"]}
                     for r in rows]
    })


@lineage_bp.route("/api/epics/assign", methods=["POST"])
def assign_epic():
    """Assign or update epic/parent_feature for one or more classifications."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    ids = data.get("ids", [])
    epic = data.get("epic", "").strip()
    parent_feature = data.get("parent_feature", "").strip()

    if not ids or not epic:
        return jsonify({"error": "ids and epic are required"}), 400

    db = get_db()
    placeholders = ",".join("?" for _ in ids)
    db.execute(
        f"UPDATE classifications SET epic=?, parent_feature=? WHERE id IN ({placeholders})",
        [epic, parent_feature] + ids
    )
    db.commit()

    return jsonify({"success": True, "updated": len(ids)})


@lineage_bp.route("/api/epics/autocomplete", methods=["GET"])
def epic_autocomplete():
    """Get autocomplete suggestions for epic names."""
    db = get_db()
    q = request.args.get("q", "").strip()

    if q:
        rows = db.execute(
            "SELECT DISTINCT epic FROM classifications WHERE epic LIKE ? AND epic != '' ORDER BY epic LIMIT 20",
            (f"%{q}%",)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT DISTINCT epic FROM classifications WHERE epic != '' ORDER BY epic LIMIT 50"
        ).fetchall()

    # Also get distinct parent features
    if q:
        feat_rows = db.execute(
            "SELECT DISTINCT parent_feature FROM classifications WHERE parent_feature LIKE ? AND parent_feature != '' ORDER BY parent_feature LIMIT 20",
            (f"%{q}%",)
        ).fetchall()
    else:
        feat_rows = db.execute(
            "SELECT DISTINCT parent_feature FROM classifications WHERE parent_feature != '' ORDER BY parent_feature LIMIT 50"
        ).fetchall()

    return jsonify({
        "epics": [r["epic"] for r in rows],
        "features": [r["parent_feature"] for r in feat_rows],
    })
