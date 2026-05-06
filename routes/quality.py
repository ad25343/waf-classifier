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

# In-memory rewrite cache: (classification_id, rubric_id) -> {rewritten, title}
# Lives for the lifetime of the process. Cleared on app restart.
_rewrite_cache: dict = {}

BATCH_SIZE = 5  # stories per AI call


# ── Rubric loader ─────────────────────────────────────────────────────────────
#
# Rubrics are now JSON files in /rubrics/, sourced from the Story Excellence
# Playbook (docs/playbook/story-excellence-v2.docx). Each rubric carries:
#   id, level (epic|feature|story|defect), phase (ready|done),
#   source_doc, source_version, source_section, scoring_mode,
#   thresholds, criteria[]
#
# Each criterion carries id/name/description/why/fix/good_example plus:
#   scored_by      = 'ai' | 'system'
#   system_check   = key into SYSTEM_CHECKS for system-scored criteria
#   required       = bool — failing a required criterion blocks 'ready'
#   weight         = float — relative weight for the overall score
#
# Backward compatibility: the old `domain` query parameter still works and
# maps to the new rubric ids via _DOMAIN_ALIASES below.

RUBRICS_DIR     = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rubrics")
BASE_DIR        = os.path.join(RUBRICS_DIR, "base")
DOMAINS_DIR     = os.path.join(RUBRICS_DIR, "domains")
MANIFEST_PATH   = os.path.join(RUBRICS_DIR, "manifest.json")

# Maps from older rubric / domain ids to the canonical level + domain pair.
# Keeps existing API callers working after the directory restructure.
_LEGACY_RUBRIC_TO_LEVEL = {
    "data_reporting": "story",
    "story-dor":      "story",
    "story":          "story",
    "feature-dor":    "feature",
    "feature":        "feature",
    "epic-dor":       "epic",
    "epic":           "epic",
    "defect-dor":     "defect",
    "defect":         "defect",
}

_rubric_cache: dict = {}


def _read_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def list_domains() -> list:
    """Read manifest.json and return the available domains."""
    manifest = _read_json(MANIFEST_PATH) or {}
    return manifest.get("domains", [])


def list_rubrics() -> list:
    """Enumerate available level rubrics (the base ones).

    Domain extensions are not standalone rubrics — they layer on top of a
    base. Use list_domains() to enumerate domains.
    """
    out = []
    if not os.path.isdir(BASE_DIR):
        return out
    for fn in sorted(os.listdir(BASE_DIR)):
        if not fn.endswith(".json"):
            continue
        r = _read_json(os.path.join(BASE_DIR, fn))
        if not r:
            continue
        out.append({
            "id":    r.get("id"),
            "level": r.get("level"),
            "phase": r.get("phase"),
            "name":  r.get("name"),
        })
    return out


def _canonical_level(rubric_or_level: str) -> str:
    """Resolve a value (e.g. 'story-dor', 'feature', 'data_reporting') to a level."""
    if not rubric_or_level:
        return "story"
    if rubric_or_level in _LEGACY_RUBRIC_TO_LEVEL:
        return _LEGACY_RUBRIC_TO_LEVEL[rubric_or_level]
    # Pattern: 'X-dor' → 'X'
    if rubric_or_level.endswith("-dor"):
        return rubric_or_level[:-4]
    return rubric_or_level


def _split_composite(rubric_id: str) -> tuple:
    """Split 'story-dor:data' into ('story', 'data'). 'story-dor' → ('story', None)."""
    if ":" in rubric_id:
        head, dom = rubric_id.split(":", 1)
        return _canonical_level(head), (dom or None)
    return _canonical_level(rubric_id), None


def _load_base(level: str) -> dict:
    """Load the universal rubric for a level."""
    path = os.path.join(BASE_DIR, f"{level}-dor.json")
    r = _read_json(path)
    if not r:
        # Fall back to story-dor if the requested level is unknown.
        r = _read_json(os.path.join(BASE_DIR, "story-dor.json")) or {"criteria": []}
    return r


def _load_extension(level: str, domain: str) -> dict:
    """Load the domain extension for a level. Returns None if absent."""
    if not domain:
        return None
    path = os.path.join(DOMAINS_DIR, domain, f"{level}-extension.json")
    return _read_json(path)


def load_rubric(rubric_id: str = None, level: str = None, domain: str = None) -> dict:
    """Load a (possibly composite) rubric.

    Two calling forms:
      load_rubric("story-dor:data")              → level=story, domain=data
      load_rubric(level="story", domain="data")  → same

    Returns a single rubric dict whose `criteria` is the union of base
    and (optional) domain extension criteria, deduped by criterion id
    with the extension overriding the base on conflict.
    """
    # Resolve level + domain
    if rubric_id and not level:
        lvl, dom = _split_composite(rubric_id)
        level = lvl
        if domain is None:
            domain = dom
    if not level:
        level = "story"
    domain = domain or None

    cache_key = f"{level}:{domain or ''}"
    if cache_key in _rubric_cache:
        return _rubric_cache[cache_key]

    base = _load_base(level)
    ext  = _load_extension(level, domain)

    # Compose
    composed = dict(base)  # shallow copy
    composed["id"] = f"{level}-dor" + (f":{domain}" if domain else "")
    composed["level"] = level
    composed["domain"] = domain
    composed["base_name"] = base.get("name")
    if ext:
        composed["extension_name"] = ext.get("name")
        composed["extension_is_placeholder"] = bool(ext.get("is_placeholder"))
        composed["extension_placeholder_note"] = ext.get("placeholder_note")
        # Append extension criteria, deduping by id (extension wins on conflict).
        seen = {c["id"]: c for c in base.get("criteria", [])}
        for c in ext.get("criteria", []):
            seen[c["id"]] = c
        composed["criteria"] = list(seen.values())

    _rubric_cache[cache_key] = composed
    return composed


def invalidate_rubric_cache():
    """Drop the rubric cache. Call after any extension JSON is edited."""
    _rubric_cache.clear()


# Legacy alias map kept for older API callers / DB rows.
# Maps: legacy value → canonical composite rubric id.
_DOMAIN_ALIASES = {
    "data_reporting": "story-dor",
    "story":          "story-dor",
    "feature":        "feature-dor",
    "epic":           "epic-dor",
    "defect":         "defect-dor",
}


def normalize_rubric_id(rubric_id: str = None, domain: str = None) -> str:
    """Build a canonical composite rubric id from input.

    Examples:
      ("story-dor", "data")     → "story-dor:data"
      ("data_reporting", None)  → "story-dor"
      ("story-dor:data", None)  → "story-dor:data"
      (None, None)              → "story-dor"
    """
    if not rubric_id:
        return "story-dor"
    rubric_id = _DOMAIN_ALIASES.get(rubric_id, rubric_id)
    # If a domain is also passed, prefer attaching it.
    if domain and ":" not in rubric_id:
        rubric_id = f"{rubric_id}:{domain}"
    return rubric_id


# ── System-check registry ─────────────────────────────────────────────────────
# Criteria with scored_by="system" don't need an AI call — they're checked
# locally using the registered function. Returns (pass: bool, optional fix str).

def _check_has_story_points(story: dict) -> tuple:
    val = story.get("story_points")
    if val is None:
        return False, None
    s = str(val).strip().lower()
    if s and s not in ("nan", "none", "null", "0", "0.0"):
        return True, None
    return False, None


SYSTEM_CHECKS = {
    "has_story_points": _check_has_story_points,
}


# ── Scoring-mode prompt fragments ─────────────────────────────────────────────
# The same rubric can be applied at three strictness levels.

_MODE_INSTRUCTIONS = {
    "lenient":  "Be practical. If you can reasonably infer a criterion is met from the context provided, mark PASS. Only FAIL if the information is clearly absent.",
    "balanced": "Pass if the criterion is clearly met OR unambiguously inferable from concrete details in the story. Fail if you would have to assume to mark it pass.",
    "strict":   "Pass ONLY if the criterion is explicitly addressed in the story with concrete details. Inference is not enough — require specifics (names, numbers, source identifiers).",
}


def _compute_score_band(criteria_results: dict, rubric: dict) -> tuple:
    """Compute (overall_score, band) per the rubric's thresholds.

    band ∈ {'ready', 'needs_work', 'not_ready'}. The 'ready' threshold can
    require all `required: true` criteria to pass via `all_required_pass`.
    """
    weighted_sum = 0.0
    total_weight = 0.0
    all_required_pass = True
    passed_count = 0
    total_count = len(rubric.get("criteria", []))

    for c in rubric.get("criteria", []):
        weight = float(c.get("weight", 1.0))
        passed = bool(criteria_results.get(c["id"], {}).get("pass", False))
        weighted_sum += weight * (1.0 if passed else 0.0)
        total_weight += weight
        if c.get("required") and not passed:
            all_required_pass = False
        if passed:
            passed_count += 1

    overall = round(weighted_sum / total_weight * 100.0, 1) if total_weight else 0.0
    th = rubric.get("thresholds", {})
    ready_th = th.get("ready", {"min_score": 89, "all_required_pass": True})
    needs_th = th.get("needs_work", {"min_score": 56})

    if (overall >= ready_th.get("min_score", 89)
        and (not ready_th.get("all_required_pass") or all_required_pass)):
        band = "ready"
    elif overall >= needs_th.get("min_score", 56):
        band = "needs_work"
    else:
        band = "not_ready"
    return overall, band, passed_count, total_count


# ── Legacy stub kept for any callers that still import RUBRICS ────────────────
# The old hard-coded RUBRICS dict is gone. If something still references it,
# it gets a thin compatibility shim that loads from the JSON files.
class _RubricsCompat(dict):
    def __getitem__(self, key):
        return load_rubric(key)
    def get(self, key, default=None):
        try:
            return load_rubric(key)
        except Exception:
            return default
RUBRICS = _RubricsCompat()


# ── AI helpers ────────────────────────────────────────────────────────────────

def _get_client():
    if AI_BACKEND == "bedrock":
        from anthropic import AnthropicBedrock
        return AnthropicBedrock()
    from anthropic import Anthropic
    return Anthropic()


def _score_batch(stories: list, rubric: dict) -> list:
    """Score a batch of stories against a rubric. Returns list of {id, criteria} dicts.

    Only AI-scored criteria are sent to the model. System-scored criteria
    (e.g. has_story_points) are checked separately by the caller.
    """
    ai_criteria = [c for c in rubric.get("criteria", []) if c.get("scored_by", "ai") != "system"]
    if not ai_criteria:
        return []

    mode = rubric.get("scoring_mode", "balanced")
    mode_text = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["balanced"])

    criteria_list = "\n".join(
        f'{i + 1}. {c["id"]}: {c["description"]}'
        for i, c in enumerate(ai_criteria)
    )
    stories_text = "\n\n".join(
        f'STORY_ID: {s["id"]}\nTitle: {s["title"]}\nDescription: {s["description"] or "(no description provided)"}'
        for s in stories
    )

    level = rubric.get("level", "story").capitalize()
    persona = (
        "epic-level reviewer for the portfolio review board" if rubric.get("level") == "epic"
        else "feature-level reviewer for program refinement" if rubric.get("level") == "feature"
        else "defect triage reviewer" if rubric.get("level") == "defect"
        else "story quality reviewer"
    )

    example_id = stories[0]["id"] if stories else "STORY_ID_HERE"
    example_first = ai_criteria[0]["id"] if ai_criteria else "criterion_id"
    example_second = ai_criteria[1]["id"] if len(ai_criteria) > 1 else example_first

    prompt = f"""You are a {persona}. You are reviewing {level} items against the Story Excellence Playbook v2 — Definition of Ready.

{mode_text}

CRITERIA:
{criteria_list}

For each criterion that FAILS, provide a short prescriptive fix (one sentence — what to add, not what is missing).

Return ONLY a JSON array — no markdown fences, no explanation:
[
  {{
    "id": "{example_id}",
    "criteria": {{
      "{example_first}": {{"pass": true}},
      "{example_second}": {{"pass": false, "fix": "Concrete one-sentence fix"}}
    }}
  }}
]

ITEMS TO SCORE:
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

def _run_scoring_job(job_id: str, classification_ids: list, rubric_id: str, job_number: int, upload_id: int, teams: list, upload_filename: str):
    """Background job that scores stories against a rubric.

    `rubric_id` is the new parameter name; legacy callers may pass the old
    `domain` value (e.g. 'data_reporting') and load_rubric() resolves it.
    """
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

        rubric = load_rubric(rubric_id)
        # Resolve to canonical id (e.g. 'data_reporting' → 'story-dor')
        canonical_id = rubric.get("id", rubric_id)
        all_criteria_ids = [c["id"] for c in rubric["criteria"]]
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
                ai_results = _score_batch(batch, rubric)
                ai_map = {r["id"]: r["criteria"] for r in ai_results}
            except Exception:
                ai_map = {}

            for r in batch_rows:
                sid = str(r["id"])
                criteria = ai_map.get(sid, {})

                # System-scored criteria — checked locally, no AI call
                story_dict = {
                    "id":             r["id"],
                    "title":          r["story_title"] or "",
                    "description":    r["story_description"] or "",
                    "story_points":   r["story_points"],
                    "team":           r["team"] or "",
                    "story_id":       r["story_id"] or "",
                }
                for c in rubric["criteria"]:
                    if c.get("scored_by") == "system":
                        check_fn = SYSTEM_CHECKS.get(c.get("system_check") or "")
                        if check_fn:
                            passed, fix_override = check_fn(story_dict)
                            criteria[c["id"]] = {"pass": passed}
                            if not passed:
                                criteria[c["id"]]["fix"] = fix_override or c.get("fix") or "Address the criterion."
                        else:
                            # Unknown system check — fail safe with the rubric's fix text
                            criteria[c["id"]] = {"pass": False, "fix": c.get("fix") or "Address the criterion."}

                # If AI returned no data, mark remaining AI criteria as unscored
                if not ai_map.get(sid):
                    for c in rubric["criteria"]:
                        if c.get("scored_by") != "system" and c["id"] not in criteria:
                            criteria[c["id"]] = {"pass": False, "fix": "Could not score — description may be empty"}

                # Weighted score + band per rubric thresholds
                overall_score, band, passed_count, total_count = _compute_score_band(criteria, rubric)

                result = {
                    "classification_id": r["id"],
                    "story_title": r["story_title"] or "",
                    "team": r["team"] or "",
                    "story_id": r["story_id"] or "",
                    "upload_id": r["upload_id"],
                    "domain": canonical_id,
                    "rubric_id": canonical_id,
                    "rubric_level": rubric.get("level", "story"),
                    "rubric_phase": rubric.get("phase", "ready"),
                    "scoring_mode": rubric.get("scoring_mode", "balanced"),
                    "band": band,
                    "overall_score": overall_score,
                    "passed_count": passed_count,
                    "total_count": total_count,
                    "criteria": criteria,
                    "description_empty": not bool((r["story_description"] or "").strip()),
                    "scored_at": scored_at,
                    "run_id": run_id,
                    "job_number": job_number,
                }
                all_results.append(result)

                # Always INSERT a new row per run (preserves run history).
                # `domain` column stores the canonical rubric_id for backward compat.
                conn.execute(
                    """INSERT INTO story_quality_scores
                       (scored_at, classification_id, upload_id, domain, overall_score,
                        passed_count, total_count, criteria_json, story_title, team,
                        story_id, run_id, job_number)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        scored_at, r["id"], r["upload_id"], canonical_id,
                        overall_score, passed_count, total_count, json.dumps(criteria),
                        result["story_title"] or "", result["team"] or "",
                        result["story_id"] or "", run_id, job_number,
                    ),
                )
                conn.commit()

            job["progress"] = min(i + BATCH_SIZE, total)
            job["results"] = all_results

        # Save run summary. Bands come from per-row `band` rather than score
        # cutoffs, so they correctly reflect the rubric's required-pass rules.
        total_scored = len(all_results)
        avg = round(sum(r["overall_score"] for r in all_results) / total_scored, 1) if total_scored else 0
        ready      = sum(1 for r in all_results if r.get("band") == "ready")
        needs_work = sum(1 for r in all_results if r.get("band") == "needs_work")
        not_ready  = sum(1 for r in all_results if r.get("band") == "not_ready")
        conn.execute(
            """INSERT OR REPLACE INTO quality_runs
               (run_id, job_number, scored_at, upload_id, upload_filename, domain,
                teams_json, story_count, avg_score, ready_count, needs_work_count, not_ready_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, job_number, scored_at, upload_id, upload_filename, canonical_id,
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
    """Return a (possibly composite) rubric definition.

    Query params (all optional):
      rubric_id  composite, e.g. 'story-dor' or 'story-dor:data'
      level      'story' | 'feature' | 'epic' | 'defect'
      domain     'data' | 'capmkts' | 'sf-origination' | 'mf-servicing' | 'risk' (or empty)

    The response also includes `available` (level rubrics) and `domains`
    (the manifest), so the UI can populate two dropdowns from one call.
    """
    rubric_id = request.args.get("rubric_id")
    level     = request.args.get("level")
    domain    = request.args.get("domain")
    # If only the legacy domain param was supplied AND it's actually a
    # legacy rubric alias (e.g. data_reporting) — treat it as rubric_id.
    if not rubric_id and not level and domain in _DOMAIN_ALIASES:
        rubric_id = domain
        domain = None

    if rubric_id:
        rubric = load_rubric(rubric_id, domain=domain)
    else:
        rubric = load_rubric(level=level, domain=domain)

    return jsonify({
        "rubric":    rubric,
        "available": list_rubrics(),
        "domains":   list_domains(),
    })


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


@quality_bp.route("/api/quality/team-of-teams", methods=["GET"])
def quality_team_of_teams():
    """Return distinct Team of Teams values for a given upload, with their teams."""
    upload_id = request.args.get("upload_id", type=int)
    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400
    db = get_db()
    rows = db.execute(
        """SELECT COALESCE(team_of_teams, '') as tot,
                  COALESCE(team, 'default') as team,
                  COUNT(*) as cnt
           FROM classifications
           WHERE upload_id=? AND team_of_teams != '' AND team_of_teams IS NOT NULL
           GROUP BY tot, team ORDER BY tot, team""",
        (upload_id,),
    ).fetchall()
    from collections import defaultdict
    tot_map = defaultdict(lambda: {"teams": [], "count": 0})
    for r in rows:
        tot_map[r["tot"]]["teams"].append({"name": r["team"], "count": r["cnt"]})
        tot_map[r["tot"]]["count"] += r["cnt"]
    result = sorted([
        {"name": tot, "teams": v["teams"], "count": v["count"]}
        for tot, v in tot_map.items()
    ], key=lambda x: x["name"])
    return jsonify({"team_of_teams": result})


@quality_bp.route("/api/quality/teams", methods=["GET"])
def quality_teams():
    upload_id = request.args.get("upload_id", type=int)
    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400
    tot_filter = request.args.get("team_of_teams", "").strip()
    db = get_db()
    if tot_filter:
        rows = db.execute(
            """SELECT COALESCE(team, 'default') as team, COUNT(*) as cnt
               FROM classifications
               WHERE upload_id=? AND COALESCE(team_of_teams,'')=?
               GROUP BY team ORDER BY team""",
            (upload_id, tot_filter),
        ).fetchall()
    else:
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
    # Accept either:
    #   {rubric_id: 'story-dor:data'}                — new composite form
    #   {rubric_id: 'story-dor', domain: 'data'}      — split form (UI sends this)
    #   {domain: 'data_reporting'}                    — legacy alias
    rubric_id = normalize_rubric_id(
        data.get("rubric_id") or data.get("domain"),
        data.get("domain") if data.get("rubric_id") else None,
    )

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
        "rubric_id": rubric_id,
        "domain": rubric_id,  # legacy alias for older clients
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
        args=(job_id, classification_ids, rubric_id, job_number, upload_id, teams, upload_filename),
        daemon=True,
    ).start()

    return jsonify({"job_id": job_id, "job_number": job_number, "total": len(classification_ids), "rubric_id": rubric_id})


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
    # Accept rubric_id (composite) OR rubric_id + domain split. Legacy
    # 'domain' alone is also accepted as a legacy alias.
    rid_in    = request.args.get("rubric_id")
    domain_in = request.args.get("domain")
    if not rid_in and domain_in in _DOMAIN_ALIASES:
        rubric_id = _DOMAIN_ALIASES[domain_in]
    else:
        rubric_id = normalize_rubric_id(rid_in, domain_in if rid_in else None)
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
        params = [upload_id, rubric_id]
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


@quality_bp.route("/api/quality/chat", methods=["POST"])
def quality_chat():
    data = request.json or {}
    classification_id = data.get("classification_id")
    rubric_id = normalize_rubric_id(
        data.get("rubric_id") or data.get("domain"),
        data.get("domain") if data.get("rubric_id") else None,
    )
    messages = data.get("messages", [])   # [{role, content}, ...]

    if not classification_id or not messages:
        return jsonify({"error": "classification_id and messages required"}), 400

    db = get_db()
    row = db.execute(
        "SELECT story_title, story_description FROM classifications WHERE id=?",
        (classification_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    rubric = load_rubric(rubric_id)
    criteria_names = [c["name"] for c in rubric["criteria"]]
    level = rubric.get("level", "story")

    system = f"""You are helping a scrum team refine a JIRA {level} against the Story Excellence Playbook v2.

ORIGINAL ITEM:
Title: {row["story_title"] or "(untitled)"}
Description:
{row["story_description"] or "(no description provided)"}

DEFINITION OF READY CRITERIA ({rubric.get('name', '')}):
{", ".join(criteria_names)}

You are in a collaborative editing session. When the user asks for changes, output the FULL updated description (not just the changed section) so they can copy it directly into JIRA.
Only use information present in or clearly inferable from the original.
Use [REQUIRED: ...] placeholders where the team must supply missing information.
Keep responses focused — lead with the updated content, add a brief explanation only if needed."""

    try:
        client = _get_client()
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=1500,
            system=system,
            messages=messages,
        )
        reply = resp.content[0].text.strip()
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quality_bp.route("/api/quality/rewrite", methods=["POST"])
def rewrite_story():
    """Generate a 'what good looks like' rewrite for a single story.

    Cached in-memory by (classification_id, rubric_id) so repeat clicks
    don't re-spend on the AI. Pass force=true to re-generate.
    """
    data = request.json or {}
    classification_id = data.get("classification_id")
    rubric_id = normalize_rubric_id(
        data.get("rubric_id") or data.get("domain"),
        data.get("domain") if data.get("rubric_id") else None,
    )
    force = bool(data.get("force"))

    if not classification_id:
        return jsonify({"error": "classification_id required"}), 400

    cache_key = (int(classification_id), rubric_id)
    if not force and cache_key in _rewrite_cache:
        cached = _rewrite_cache[cache_key]
        return jsonify({"rewritten": cached["rewritten"], "title": cached["title"], "cached": True})

    db = get_db()
    row = db.execute(
        "SELECT story_title, story_description, story_points FROM classifications WHERE id=?",
        (classification_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Story not found"}), 404

    rubric = load_rubric(rubric_id)

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

    # Build a rubric-driven structural template — one section per criterion,
    # using each criterion's good_example as guidance. Works for any rubric
    # (story, feature, epic, defect) without hardcoded story-specific sections.
    structure_lines = []
    for c in rubric.get("criteria", []):
        # Skip system-checked criteria like "Story Pointed" — those aren't
        # in the description, they're metadata.
        if c.get("scored_by") == "system":
            continue
        structure_lines.append(f"**{c['name']}**")
        structure_lines.append(
            f"[Address per: {c.get('good_example', c.get('description', '')).strip()} — or insert REQUIRED placeholder]"
        )
        structure_lines.append("")
    structure_block = "\n".join(structure_lines).rstrip()

    level = rubric.get("level", "story")

    prompt = f"""You are helping a scrum team improve a JIRA {level} against the Story Excellence Playbook v2.

ORIGINAL {level.upper()}:
Title: {row["story_title"] or "(untitled)"}
Description:
{row["story_description"] or "(no description provided)"}

GAPS IDENTIFIED ({rubric.get('name', 'Definition of Ready')}):
{gaps_text}

TASK: Rewrite the description to address the gaps above.

CRITICAL RULES:
1. Only use information present in or clearly inferable from the original.
2. Do NOT invent source systems, calculations, business rules, or data not mentioned.
3. Where required information is absent, insert a placeholder like: [REQUIRED: specify <what>].
4. Keep all original intent and context.
5. Output only the rewritten content — no preamble, no explanation.

Use this structure (one section per Definition-of-Ready criterion):

{structure_block}"""

    try:
        client = _get_client()
        resp = client.messages.create(
            model=AI_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        rewritten = resp.content[0].text.strip()
        # Cache so re-clicks (and the post-click read) don't re-spend on AI.
        _rewrite_cache[cache_key] = {
            "rewritten": rewritten,
            "title": row["story_title"] or "",
        }
        return jsonify({"rewritten": rewritten, "title": row["story_title"], "cached": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@quality_bp.route("/api/quality/export", methods=["GET"])
def quality_export():
    upload_id = request.args.get("upload_id", type=int)
    teams_raw = request.args.get("teams", "")
    rid_in    = request.args.get("rubric_id")
    domain_in = request.args.get("domain")
    if not rid_in and domain_in in _DOMAIN_ALIASES:
        rubric_id = _DOMAIN_ALIASES[domain_in]
    else:
        rubric_id = normalize_rubric_id(rid_in, domain_in if rid_in else None)

    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    teams = [t.strip() for t in teams_raw.split(",") if t.strip()] if teams_raw else []

    db = get_db()
    where = "s.upload_id=? AND s.domain=?"
    params = [upload_id, rubric_id]
    if teams:
        placeholders = ",".join("?" * len(teams))
        where += f" AND s.team IN ({placeholders})"
        params.extend(teams)

    rows = db.execute(
        f"SELECT s.* FROM story_quality_scores s WHERE {where} ORDER BY s.overall_score ASC",
        params,
    ).fetchall()

    rubric = load_rubric(rubric_id)
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


# ── Domain extension editor endpoints ────────────────────────────────────────
# Lets domain stewards review, edit, and reset the JSON extensions from the UI.

_VALID_LEVELS = {"story", "feature", "epic", "defect"}


def _extension_path(domain: str, level: str) -> str:
    """Resolve the on-disk path for a domain+level extension. Validates inputs."""
    if not domain or not isinstance(domain, str) or "/" in domain or ".." in domain:
        raise ValueError("invalid domain id")
    if level not in _VALID_LEVELS:
        raise ValueError(f"level must be one of {sorted(_VALID_LEVELS)}")
    return os.path.join(DOMAINS_DIR, domain, f"{level}-extension.json")


def _backup_path(path: str) -> str:
    """Sibling path used to stash the previous version when an extension is saved."""
    return path + ".bak"


@quality_bp.route("/api/quality/extension", methods=["GET"])
def get_extension():
    """Return the raw JSON of a domain extension for editing.

    Query params: domain, level
    """
    domain = (request.args.get("domain") or "").strip()
    level  = (request.args.get("level")  or "").strip()
    try:
        path = _extension_path(domain, level)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    raw = _read_json(path)
    if raw is None:
        return jsonify({"error": "Extension not found", "domain": domain, "level": level}), 404
    return jsonify({
        "domain": domain,
        "level":  level,
        "extension": raw,
        "path": os.path.relpath(path, RUBRICS_DIR),
        "has_backup": os.path.exists(_backup_path(path)),
    })


@quality_bp.route("/api/quality/extension", methods=["PUT"])
def put_extension():
    """Save (overwrite) a domain extension.

    Body:
      { domain: 'data', level: 'story', extension: { ... full JSON ... } }

    The existing file (if any) is backed up to <path>.bak before write.
    The rubric cache is invalidated so the next /api/quality/rubric call
    sees the new content.
    """
    data = request.json or {}
    domain    = (data.get("domain") or "").strip()
    level     = (data.get("level")  or "").strip()
    extension = data.get("extension")
    if not isinstance(extension, dict):
        return jsonify({"error": "extension must be a JSON object"}), 400
    try:
        path = _extension_path(domain, level)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Sanity-check the structure: must have criteria array; each criterion needs
    # at least id and name. Anything malformed is rejected before we touch disk.
    if not isinstance(extension.get("criteria"), list):
        return jsonify({"error": "extension.criteria must be a list"}), 400
    seen_ids = set()
    for i, c in enumerate(extension["criteria"]):
        if not isinstance(c, dict):
            return jsonify({"error": f"criteria[{i}] must be an object"}), 400
        cid = (c.get("id") or "").strip()
        if not cid:
            return jsonify({"error": f"criteria[{i}].id is required"}), 400
        if cid in seen_ids:
            return jsonify({"error": f"duplicate criterion id: {cid!r}"}), 400
        seen_ids.add(cid)
        if not (c.get("name") or "").strip():
            return jsonify({"error": f"criteria[{i}].name is required"}), 400

    # Stamp metadata so the UI can surface it
    extension["domain"] = domain
    extension["level"]  = level
    extension["phase"]  = extension.get("phase", "ready")

    # Ensure parent directory exists (creating a domain on first save)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Backup the existing file before overwriting
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                prev = fh.read()
            with open(_backup_path(path), "w", encoding="utf-8") as fh:
                fh.write(prev)
        except Exception as e:
            return jsonify({"error": f"backup failed: {e}"}), 500

    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(extension, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except Exception as e:
        return jsonify({"error": f"write failed: {e}"}), 500

    invalidate_rubric_cache()
    return jsonify({"success": True, "path": os.path.relpath(path, RUBRICS_DIR)})


@quality_bp.route("/api/quality/extension/reset", methods=["POST"])
def reset_extension():
    """Restore a domain extension from its .bak backup, if one exists.

    Body: { domain, level }
    """
    data = request.json or {}
    domain = (data.get("domain") or "").strip()
    level  = (data.get("level")  or "").strip()
    try:
        path = _extension_path(domain, level)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    bak = _backup_path(path)
    if not os.path.exists(bak):
        return jsonify({"error": "no backup found for this extension"}), 404
    try:
        with open(bak, "r", encoding="utf-8") as fh:
            content = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    except Exception as e:
        return jsonify({"error": f"restore failed: {e}"}), 500

    invalidate_rubric_cache()
    return jsonify({"success": True})
