"""
Story Quality scoring routes.
Scores stories against the Definition of Ready rubric (GSE-MF Story Excellence Playbook).
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, Response

from config import AI_BACKEND, AI_MODEL, DB_PATH
from database import get_db

quality_bp = Blueprint("quality_bp", __name__)

# In-memory job store: job_id -> {status, progress, total, results, error}
_quality_jobs: dict = {}
_quality_job_counter: int = 0

BATCH_SIZE = 5  # stories per AI call


# ── Rubric definition ─────────────────────────────────────────────────────────

RUBRICS = {
    "data_reporting": {
        "id": "data_reporting",
        "name": "Data & Reporting",
        "full_name": "Data, Reporting & Analytics — Definition of Ready",
        "source": "GSE-MF Story Excellence Playbook v1.0",
        "description": (
            "9-criterion checklist ensuring every data and reporting story is independently "
            "deliverable before it enters a sprint. A developer should be able to pick it up "
            "on Monday and deliver by Friday with no open questions."
        ),
        "criteria": [
            {
                "id": "narrative",
                "name": "Narrative Format",
                "description": "Story uses 'As a [role] / I need [capability] / So that [outcome]' format",
                "why": "Anchors the work to a stakeholder need and a measurable business outcome.",
                "good_example": "As a Senior Risk Analyst / I need a portfolio delinquency rate dashboard filtered by property type and loan vintage / So that I can produce the weekly risk committee slide pack without manual data pulls",
                "fix": "Rewrite the opening as: As a [stakeholder role] / I need [specific capability] / So that [business outcome]",
            },
            {
                "id": "source_data",
                "name": "Source Data Identified",
                "description": "Specific source table, feed, API, or system is named with owner and refresh frequency",
                "why": "Prevents mid-sprint clarification cycles when a developer can't find the data.",
                "good_example": "Table: dw.loan_performance_monthly, System: EDW, Refresh: Nightly 02:00 EST. Known issue: NULL vintage_year = treat as Pre-2015 bucket",
                "fix": "Add the source table/feed name, owning system, refresh schedule, and any known data quality issues",
            },
            {
                "id": "business_rules",
                "name": "Business Rules Documented",
                "description": "Transformation logic, GSE/MF-specific definitions, calculations, and edge cases are written out explicitly — not just referenced",
                "why": "Vague references to 'standard logic' cause rework when assumptions differ.",
                "good_example": "Delinquency rate = loans 30+ DPD / total active loans. reporting_date = last business day of prior month. Property types: MF, SR, HC. Exclude Paid Off and REO.",
                "fix": "Write out the exact calculation, key definitions used by the team, and how edge cases (nulls, exclusions, rounding) are handled",
            },
            {
                "id": "output_artifact",
                "name": "Output Artifact Defined",
                "description": "The deliverable (dashboard, report, table, flat file, API) is clearly specified with schema or mockup",
                "why": "Without a specified artifact, the developer and PO may have different expectations at demo.",
                "good_example": "Dashboard: portfolio delinquency rate filtered by property type and loan vintage. Columns: loan_id, reporting_date, delinquency_rate, property_type. Mockup: [Confluence link]",
                "fix": "Specify the exact deliverable type and include a column list, schema sketch, or mockup link",
            },
            {
                "id": "acceptance_criteria",
                "name": "Acceptance Criteria",
                "description": "Binary, independently testable acceptance criteria are present (AC1, AC2... format)",
                "why": "Subjective AC generates PO rejection at demo — binary AC makes the definition of done concrete.",
                "good_example": "AC1: MF delinquency rate for March 2026 matches EDW query within 0.01%. AC2: Filtering by property type returns only loans in that type. AC3: Dashboard loads in under 3 seconds.",
                "fix": "Add AC1, AC2... statements that are binary (pass/fail), specific, and independently testable by a tester without ambiguity",
            },
            {
                "id": "data_quality",
                "name": "Data Quality Checks",
                "description": "Row count reconciliation, null checks, and referential integrity requirements are specified",
                "why": "Data quality failures discovered late in the sprint cause last-minute rework and pipeline rollbacks.",
                "good_example": "Row count reconciles to dw.loan_performance_monthly within 0.01%. No nulls in loan_id or reporting_date. Ref integrity: loan_id must exist in dw.loans.",
                "fix": "Add: row count tolerance, which key columns must be non-null, and any foreign key / referential integrity checks required",
            },
            {
                "id": "traceability",
                "name": "Traceability Tag",
                "description": "Data lineage documented as Source → Transformation Layer → Output Artifact → Business Consumer",
                "why": "Enables impact analysis when upstream sources change and supports audit/regulatory requirements.",
                "good_example": "EDW.dw.loan_performance → Analytics Mart → Delinquency Dashboard → Risk Committee (weekly pack)",
                "fix": "Add a single traceability line: [Source System] → [Transformation Layer] → [Output Artifact] → [Business Consumer]",
            },
            {
                "id": "story_points",
                "name": "Story Pointed",
                "description": "Story has been estimated in story points by the team during refinement or planning",
                "why": "Unpointed stories cannot be planned into a sprint — they are invisible to capacity planning.",
                "good_example": "Story Points: 3",
                "fix": "Estimate the story in story points at the next refinement or planning session",
            },
            {
                "id": "dependencies",
                "name": "Dependencies Flagged",
                "description": "Upstream data readiness requirements and downstream consumer dependencies are noted",
                "why": "Undocumented dependencies create blocking surprises mid-sprint.",
                "good_example": "Upstream: dw.loan_performance available by T+1 (confirmed with EDW team). Downstream: Risk committee slide pack produced weekly by Analyst team.",
                "fix": "Add upstream dependencies (data feeds, other stories, external teams) and downstream consumers (reports, dashboards, teams) that depend on this work",
            },
        ],
    }
}


# ── AI helpers ────────────────────────────────────────────────────────────────

def _get_client():
    if AI_BACKEND == "bedrock":
        from anthropic import AnthropicBedrock
        return AnthropicBedrock()
    from anthropic import Anthropic
    return Anthropic()


def _score_batch(stories: list, domain: str) -> list:
    """Score a batch of stories. Returns list of {id, criteria} dicts."""
    rubric = RUBRICS.get(domain, RUBRICS["data_reporting"])
    ai_criteria = [c for c in rubric["criteria"] if c["id"] != "story_points"]

    criteria_list = "\n".join(
        f'{i + 1}. {c["id"]}: {c["description"]}'
        for i, c in enumerate(ai_criteria)
    )
    stories_text = "\n\n".join(
        f'STORY_ID: {s["id"]}\nTitle: {s["title"]}\nDescription: {s["description"] or "(no description provided)"}'
        for s in stories
    )

    prompt = f"""You are a story quality reviewer for a Data, Reporting and Analytics team.

Score each story against these Definition of Ready criteria. Be practical — if you can reasonably infer a criterion is met from the context provided, mark PASS. Only FAIL if the information is clearly absent.

CRITERIA:
{criteria_list}

For each criterion that FAILS, provide a short prescriptive fix (one sentence — what to add, not what is missing).

Return ONLY a JSON array — no markdown fences, no explanation:
[
  {{
    "id": "STORY_ID_HERE",
    "criteria": {{
      "narrative": {{"pass": true}},
      "source_data": {{"pass": false, "fix": "Add the source table name and owning system (e.g. dw.loan_performance, EDW)"}}
    }}
  }}
]

STORIES TO SCORE:
{stories_text}"""

    client = _get_client()
    resp = client.messages.create(
        model=AI_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    return json.loads(raw)


# ── Background job ─────────────────────────────────────────────────────────────

def _run_scoring_job(job_id: str, classification_ids: list, domain: str, job_number: int, upload_id: int, teams: list, upload_filename: str):
    job = _quality_jobs[job_id]
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), DB_PATH) if not os.path.isabs(DB_PATH) else DB_PATH
    run_id = job_id
    scored_at = datetime.now().isoformat()

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        placeholders = ",".join("?" * len(classification_ids))
        rows = conn.execute(
            f"""SELECT id, story_title, story_description, story_points, team, story_id, upload_id
                FROM classifications WHERE id IN ({placeholders})""",
            classification_ids,
        ).fetchall()

        total = len(rows)
        job["total"] = total
        job["status"] = "running"

        rubric = RUBRICS.get(domain, RUBRICS["data_reporting"])
        all_criteria_ids = [c["id"] for c in rubric["criteria"]]
        total_criteria = len(all_criteria_ids)
        all_results = []

        for i in range(0, total, BATCH_SIZE):
            batch_rows = rows[i : i + BATCH_SIZE]
            batch = [
                {
                    "id": str(r["id"]),
                    "title": r["story_title"] or "",
                    "description": r["story_description"] or "",
                }
                for r in batch_rows
            ]

            try:
                ai_results = _score_batch(batch, domain)
                ai_map = {r["id"]: r["criteria"] for r in ai_results}
            except Exception:
                ai_map = {}

            for r in batch_rows:
                sid = str(r["id"])
                criteria = ai_map.get(sid, {})

                # story_points: scored without AI
                has_points = bool(r["story_points"] and str(r["story_points"]).strip())
                criteria["story_points"] = {
                    "pass": has_points,
                    **({"fix": "Estimate in story points at the next refinement or planning session"} if not has_points else {}),
                }

                # If AI returned no data, mark all AI criteria as unscored
                if not ai_map.get(sid):
                    for c in rubric["criteria"]:
                        if c["id"] != "story_points" and c["id"] not in criteria:
                            criteria[c["id"]] = {"pass": False, "fix": "Could not score — description may be empty"}

                passed = sum(1 for cid in all_criteria_ids if criteria.get(cid, {}).get("pass", False))
                overall_score = round(passed / total_criteria * 100, 1) if total_criteria else 0

                result = {
                    "classification_id": r["id"],
                    "story_title": r["story_title"] or "",
                    "team": r["team"] or "",
                    "story_id": r["story_id"] or "",
                    "upload_id": r["upload_id"],
                    "domain": domain,
                    "overall_score": overall_score,
                    "passed_count": passed,
                    "total_count": total_criteria,
                    "criteria": criteria,
                    "description_empty": not bool((r["story_description"] or "").strip()),
                    "scored_at": scored_at,
                    "run_id": run_id,
                    "job_number": job_number,
                }
                all_results.append(result)

                # Always INSERT a new row per run (preserves run history)
                conn.execute(
                    """INSERT INTO story_quality_scores
                       (scored_at, classification_id, upload_id, domain, overall_score,
                        passed_count, total_count, criteria_json, story_title, team,
                        story_id, run_id, job_number)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        scored_at, r["id"], r["upload_id"], domain,
                        overall_score, passed, total_criteria, json.dumps(criteria),
                        result["story_title"] or "", result["team"] or "",
                        result["story_id"] or "", run_id, job_number,
                    ),
                )
                conn.commit()

            job["progress"] = min(i + BATCH_SIZE, total)
            job["results"] = all_results

        # Save run summary
        total_scored = len(all_results)
        avg = round(sum(r["overall_score"] for r in all_results) / total_scored, 1) if total_scored else 0
        ready = sum(1 for r in all_results if r["overall_score"] >= 89)
        needs_work = sum(1 for r in all_results if 56 <= r["overall_score"] < 89)
        not_ready = sum(1 for r in all_results if r["overall_score"] < 56)
        conn.execute(
            """INSERT OR REPLACE INTO quality_runs
               (run_id, job_number, scored_at, upload_id, upload_filename, domain,
                teams_json, story_count, avg_score, ready_count, needs_work_count, not_ready_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, job_number, scored_at, upload_id, upload_filename, domain,
             json.dumps(teams), total_scored, avg, ready, needs_work, not_ready),
        )
        conn.commit()

        job["status"] = "complete"
        job["results"] = all_results

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── API routes ─────────────────────────────────────────────────────────────────

@quality_bp.route("/api/quality/rubric", methods=["GET"])
def get_rubric():
    domain = request.args.get("domain", "data_reporting")
    rubric = RUBRICS.get(domain, RUBRICS["data_reporting"])
    return jsonify({"rubric": rubric, "domains": [{"id": k, "name": v["name"]} for k, v in RUBRICS.items()]})


@quality_bp.route("/api/quality/uploads", methods=["GET"])
def quality_uploads():
    db = get_db()
    rows = db.execute(
        """SELECT h.id, h.filename, h.uploaded_at,
                  COUNT(c.id) as story_count,
                  COUNT(DISTINCT c.team) as team_count
           FROM upload_history h
           JOIN classifications c ON c.upload_id = h.id
           GROUP BY h.id
           ORDER BY h.uploaded_at DESC"""
    ).fetchall()
    return jsonify({
        "uploads": [
            {
                "upload_id": r["id"],
                "filename": r["filename"],
                "uploaded_at": r["uploaded_at"],
                "story_count": r["story_count"],
                "team_count": r["team_count"],
            }
            for r in rows
        ]
    })


@quality_bp.route("/api/quality/teams", methods=["GET"])
def quality_teams():
    upload_id = request.args.get("upload_id", type=int)
    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400
    db = get_db()
    rows = db.execute(
        """SELECT COALESCE(team, 'default') as team, COUNT(*) as cnt
           FROM classifications
           WHERE upload_id=?
           GROUP BY team ORDER BY team""",
        (upload_id,),
    ).fetchall()
    return jsonify({"teams": [{"name": r["team"], "count": r["cnt"]} for r in rows]})


@quality_bp.route("/api/quality/score", methods=["POST"])
def start_scoring():
    data = request.json or {}
    upload_id = data.get("upload_id")
    teams = data.get("teams", [])
    domain = data.get("domain", "data_reporting")

    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    db = get_db()
    where = "upload_id = ?"
    params = [upload_id]
    if teams:
        placeholders = ",".join("?" * len(teams))
        where += f" AND COALESCE(team,'default') IN ({placeholders})"
        params.extend(teams)

    rows = db.execute(f"SELECT id FROM classifications WHERE {where}", params).fetchall()
    if not rows:
        return jsonify({"error": "No stories found for the selected upload and teams"}), 404

    global _quality_job_counter
    _quality_job_counter += 1
    job_number = _quality_job_counter

    classification_ids = [r["id"] for r in rows]
    job_id = str(uuid.uuid4())[:8]
    _quality_jobs[job_id] = {
        "status": "pending",
        "job_number": job_number,
        "progress": 0,
        "total": len(classification_ids),
        "results": [],
        "error": None,
        "domain": domain,
        "upload_id": upload_id,
        "teams": teams,
    }

    # Get upload filename for run record
    upload_filename = get_db().execute(
        "SELECT filename FROM upload_history WHERE id=?", (upload_id,)
    ).fetchone()
    upload_filename = upload_filename["filename"] if upload_filename else ""

    threading.Thread(
        target=_run_scoring_job,
        args=(job_id, classification_ids, domain, job_number, upload_id, teams, upload_filename),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "job_number": job_number, "total": len(classification_ids)})


@quality_bp.route("/api/quality/job/<job_id>", methods=["GET"])
def quality_job_status(job_id):
    job = _quality_jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": job["status"],
        "job_number": job.get("job_number"),
        "progress": job["progress"],
        "total": job["total"],
        "results": job.get("results", []),
        "error": job.get("error"),
    })


@quality_bp.route("/api/quality/results", methods=["GET"])
def quality_results():
    upload_id = request.args.get("upload_id", type=int)
    teams_raw = request.args.get("teams", "")
    domain = request.args.get("domain", "data_reporting")
    run_id = request.args.get("run_id")

    if not upload_id and not run_id:
        return jsonify({"error": "upload_id or run_id required"}), 400

    teams = [t.strip() for t in teams_raw.split(",") if t.strip()] if teams_raw else []

    db = get_db()
    if run_id:
        where = "s.run_id=?"
        params = [run_id]
    else:
        where = "s.upload_id=? AND s.domain=?"
        params = [upload_id, domain]
        if teams:
            placeholders = ",".join("?" * len(teams))
            where += f" AND s.team IN ({placeholders})"
            params.extend(teams)

    rows = db.execute(
        f"""SELECT s.*, c.story_description
            FROM story_quality_scores s
            JOIN classifications c ON c.id = s.classification_id
            WHERE {where}
            ORDER BY s.overall_score ASC""",
        params,
    ).fetchall()

    results = [
        {
            "classification_id": r["classification_id"],
            "story_title": r["story_title"],
            "team": r["team"],
            "story_id": r["story_id"],
            "overall_score": r["overall_score"],
            "passed_count": r["passed_count"],
            "total_count": r["total_count"],
            "criteria": json.loads(r["criteria_json"] or "{}"),
            "scored_at": r["scored_at"],
            "description_empty": not bool((r["story_description"] or "").strip()),
        }
        for r in rows
    ]
    return jsonify({"results": results, "count": len(results)})


@quality_bp.route("/api/quality/history", methods=["GET"])
def quality_history():
    db = get_db()
    rows = db.execute(
        """SELECT * FROM quality_runs ORDER BY scored_at DESC"""
    ).fetchall()
    return jsonify({
        "runs": [
            {
                "run_id": r["run_id"],
                "job_number": r["job_number"],
                "scored_at": r["scored_at"],
                "upload_id": r["upload_id"],
                "upload_filename": r["upload_filename"],
                "domain": r["domain"],
                "teams": json.loads(r["teams_json"] or "[]"),
                "story_count": r["story_count"],
                "avg_score": r["avg_score"],
                "ready_count": r["ready_count"],
                "needs_work_count": r["needs_work_count"],
                "not_ready_count": r["not_ready_count"],
            }
            for r in rows
        ]
    })


@quality_bp.route("/api/quality/history/<run_id>", methods=["DELETE"])
def delete_quality_run(run_id):
    db = get_db()
    db.execute("DELETE FROM story_quality_scores WHERE run_id=?", (run_id,))
    db.execute("DELETE FROM quality_runs WHERE run_id=?", (run_id,))
    db.commit()
    return jsonify({"ok": True})


@quality_bp.route("/api/quality/rewrite", methods=["POST"])
def rewrite_story():
    data = request.json or {}
    classification_id = data.get("classification_id")
    domain = data.get("domain", "data_reporting")

    if not classification_id:
        return jsonify({"error": "classification_id required"}), 400

    db = get_db()
    row = db.execute(
        "SELECT story_title, story_description, story_points FROM classifications WHERE id=?",
        (classification_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    rubric = RUBRICS.get(domain, RUBRICS["data_reporting"])

    # Get the most recent score for context on failing criteria
    score_row = db.execute(
        "SELECT criteria_json FROM story_quality_scores WHERE classification_id=? ORDER BY scored_at DESC LIMIT 1",
        (classification_id,),
    ).fetchone()

    failing_criteria = []
    if score_row:
        criteria = json.loads(score_row["criteria_json"] or "{}")
        for c in rubric["criteria"]:
            crit = criteria.get(c["id"], {})
            if not crit.get("pass", False):
                failing_criteria.append({
                    "name": c["name"],
                    "fix": crit.get("fix") or c["fix"],
                    "good_example": c["good_example"],
                })

    if failing_criteria:
        gaps_text = "\n".join(
            f'- {c["name"]}: {c["fix"]}'
            for c in failing_criteria
        )
    else:
        gaps_text = "Review all criteria and improve where possible."

    prompt = f"""You are helping a scrum team improve a JIRA story for a Data, Reporting and Analytics team.

ORIGINAL STORY:
Title: {row["story_title"] or "(untitled)"}
Description:
{row["story_description"] or "(no description provided)"}

GAPS IDENTIFIED:
{gaps_text}

TASK: Rewrite the story description to address the gaps above.

CRITICAL RULES:
1. Only use information present in or clearly inferable from the original story.
2. Do NOT invent source tables, system names, calculations, or business rules not mentioned.
3. Where required information is absent, insert a placeholder like: [REQUIRED: specify source table and owning system]
4. Keep all original intent and context.
5. Output only the rewritten description — no preamble, no explanation.

Use this structure:

**As a** [role]
**I need** [capability]
**So that** [business outcome]

---
**Source Data**
[table/feed, owning system, refresh schedule — or REQUIRED placeholder]

**Business Rules & Calculations**
[transformations, key definitions, edge cases — or REQUIRED placeholder]

**Output Artifact**
[dashboard/report/table/file type and column list — or REQUIRED placeholder]

**Acceptance Criteria**
AC1: [binary, testable]
AC2: [binary, testable]

**Data Quality Checks**
[row count tolerance, null checks, referential integrity — or REQUIRED placeholder]

**Data Lineage**
[Source System] → [Transformation Layer] → [Output Artifact] → [Business Consumer]

**Dependencies**
Upstream: [data feeds, other stories, external teams — or "None identified"]
Downstream: [consumers — or "None identified"]"""

    try:
        client = _get_client()
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        rewritten = resp.content[0].text.strip()
        return jsonify({"rewritten": rewritten, "title": row["story_title"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quality_bp.route("/api/quality/export", methods=["GET"])
def quality_export():
    upload_id = request.args.get("upload_id", type=int)
    teams_raw = request.args.get("teams", "")
    domain = request.args.get("domain", "data_reporting")

    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    teams = [t.strip() for t in teams_raw.split(",") if t.strip()] if teams_raw else []

    db = get_db()
    where = "s.upload_id=? AND s.domain=?"
    params = [upload_id, domain]
    if teams:
        placeholders = ",".join("?" * len(teams))
        where += f" AND s.team IN ({placeholders})"
        params.extend(teams)

    rows = db.execute(
        f"SELECT s.* FROM story_quality_scores s WHERE {where} ORDER BY s.overall_score ASC",
        params,
    ).fetchall()

    rubric = RUBRICS.get(domain, RUBRICS["data_reporting"])
    criteria_ids = [c["id"] for c in rubric["criteria"]]
    criteria_names = [c["name"] for c in rubric["criteria"]]

    def q(s):
        return '"' + str(s or "").replace('"', "'") + '"'

    header = "Story ID,Story Title,Team,Score %,Passed,Total," + ",".join(criteria_names) + ",Scored At"
    lines = [header]
    for r in rows:
        criteria = json.loads(r["criteria_json"] or "{}")
        cells = []
        for cid in criteria_ids:
            c = criteria.get(cid, {})
            if not c:
                cells.append("N/A")
            elif c.get("pass"):
                cells.append("PASS")
            else:
                cells.append(f'FAIL: {c.get("fix", "")}')
        lines.append(
            f'{q(r["story_id"])},{q(r["story_title"])},{q(r["team"])},'
            f'{r["overall_score"]},{r["passed_count"]},{r["total_count"]},'
            + ",".join(q(c) for c in cells)
            + f',{q(r["scored_at"])}'
        )

    return Response(
        "\n".join(lines),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="story_quality_{upload_id}.csv"'},
    )
