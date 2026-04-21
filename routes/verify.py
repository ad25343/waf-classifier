"""
Bulk-verify routes: preview upload, async classification, status polling, save.
"""

import os
import re
import json
import threading
import uuid
import time as _time
import logging
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from state import verify_jobs, _preview_store, _PREVIEW_TTL, waf_store, ground_truth_store
from config import AI_MODEL, UPLOAD_FOLDER
from database import get_db, save_classification, get_setting
from waf_core import get_client, build_system_prompt, build_system_prompt_for_versions, normalize_waf_category, _check_rate_limit

logger = logging.getLogger(__name__)

verify_bp = Blueprint("verify_bp", __name__)

# Need DB_PATH for the background thread (can't use Flask g outside request)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "waf_history.db")

# ── Helpers ───────────────────────────────────────────────────────────

_JOB_TTL = 2 * 60 * 60  # 2 hours — evict completed/errored jobs after this


def _find_col(df_columns, keywords):
    """Return the first column name matching any keyword (substring, priority order)."""
    for kw in keywords:
        for col in df_columns:
            if kw in col:
                return col
    return None


def _cleanup_previews():
    """Remove expired previews."""
    now = _time.time()
    expired = [k for k, v in _preview_store.items() if now - v["created"] > _PREVIEW_TTL]
    for k in expired:
        del _preview_store[k]


def _cleanup_jobs():
    """Evict completed/errored jobs older than _JOB_TTL to prevent unbounded memory growth."""
    cutoff = (datetime.now() - timedelta(seconds=_JOB_TTL)).isoformat()
    stale = [jid for jid, j in list(verify_jobs.items())
             if j["status"] in ("done", "error") and j.get("started_at", "9") < cutoff]
    for jid in stale:
        del verify_jobs[jid]


def _classify_single_batch(batch, batch_offset, system_prompt, api_key, job_id_short):
    """Classify a single batch of stories. Returns list of result dicts."""
    from anthropic import Anthropic
    try:
        from anthropic import AnthropicBedrock as _AnthropicBedrock
        _BEDROCK_AVAILABLE = True
    except ImportError:
        _BEDROCK_AVAILABLE = False

    # Async worker passes the raw API key; use Bedrock when it's absent
    if api_key:
        client = Anthropic(api_key=api_key)
    elif _BEDROCK_AVAILABLE:
        aws_region = os.environ.get("AWS_DEFAULT_REGION",
                                    os.environ.get("AWS_REGION", "us-east-1"))
        client = _AnthropicBedrock(aws_region=aws_region)
    else:
        raise RuntimeError("No ANTHROPIC_API_KEY and AnthropicBedrock not available")
    batch_prompt = "Classify each story below into the correct WAF category. For EACH story, respond with EXACTLY this format on separate lines:\n\n"
    batch_prompt += "STORY 1: [WAF Category] | [WAF Sub-Category] | [WAF Color] | [Run or Change] | [Confidence: HIGH/MEDIUM/LOW] | [One-line reasoning]\n\n"
    batch_prompt += "If a story has no description, set Confidence to LOW and note that classification is based on title only.\n\n"
    batch_prompt += "Here are the stories:\n\n"
    for j, s in enumerate(batch, 1):
        batch_prompt += f"STORY {j}: {s['title']}"
        if s["description"] and s["description"].strip() and s["description"].strip().lower() != "nan":
            batch_prompt += f"\nDescription: {s['description'][:300]}"
        else:
            batch_prompt += "\nDescription: (none provided)"
        batch_prompt += "\n\n"

    try:
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": batch_prompt}]
        )
        ai_text = response.content[0].text

        ai_lines = []
        for l in ai_text.split("\n"):
            stripped = l.strip().replace("**", "").replace("*", "")
            if re.match(r'^STORY\s+\d+', stripped, re.IGNORECASE):
                ai_lines.append(stripped)

        results = []
        for j, s in enumerate(batch):
            ai_cat = ai_color = ai_rc = ai_conf = ai_reason = ai_subcat = ""
            if j < len(ai_lines):
                parts = ai_lines[j].split("|")
                first_part = parts[0] if parts else ""
                colon_idx = first_part.find(":")
                if colon_idx >= 0:
                    first_part = first_part[colon_idx + 1:]
                if len(parts) >= 1: ai_cat = first_part.strip()
                if len(parts) >= 2: ai_subcat = parts[1].strip()
                if len(parts) >= 3: ai_color = parts[2].strip()
                if len(parts) >= 4: ai_rc = parts[3].strip()
                if len(parts) >= 5: ai_conf = parts[4].strip().replace("Confidence:", "").strip()
                if len(parts) >= 6: ai_reason = parts[5].strip()

            norm_cat, was_normalized, orig_cat = normalize_waf_category(s["user_submitted_waf"])
            if s["user_submitted_waf"] and ai_cat:
                is_match = norm_cat.lower().strip() == ai_cat.lower().strip()
            else:
                is_match = None

            missing_desc = not s["description"] or s["description"].strip() == "" or s["description"].strip().lower() == "nan"
            if missing_desc:
                ai_conf = "LOW"
                if ai_reason:
                    ai_reason = ai_reason + " [No description — title only]"
                else:
                    ai_reason = "No description provided — classified on title only"

            results.append({
                "index": batch_offset + j,
                "title": s["title"], "description": s["description"][:200],
                "missing_description": missing_desc,
                "team": s["team"], "epic": s["epic"], "parent_feature": s["parent_feature"],
                "story_id": s.get("story_id", ""), "feature_id": s.get("feature_id", ""), "epic_id": s.get("epic_id", ""),
                "story_points": s.get("story_points", ""),
                "timestamp": s["timestamp"], "user_submitted_waf": s["user_submitted_waf"],
                "user_submitted_waf_normalized": norm_cat if was_normalized else "",
                "was_normalized": was_normalized,
                "file_color": s["file_color"], "file_run_change": s["file_run_change"],
                "file_subcategory": s.get("file_subcategory", ""), "file_confidence": s.get("file_confidence", ""),
                "ai_suggested_waf": ai_cat, "ai_subcategory": ai_subcat, "ai_color": ai_color,
                "ai_run_change": ai_rc, "ai_confidence": ai_conf, "ai_reason": ai_reason,
                "is_match": is_match,
            })
        return results
    except Exception as e:
        print(f"[BULK-VERIFY][{job_id_short}] ERROR: {type(e).__name__}: {str(e)[:300]}")
        results = []
        for j, s in enumerate(batch):
            results.append({
                "index": batch_offset + j,
                "title": s["title"], "description": s["description"][:200],
                "team": s["team"], "epic": s["epic"], "parent_feature": s["parent_feature"],
                "story_id": s.get("story_id", ""), "feature_id": s.get("feature_id", ""), "epic_id": s.get("epic_id", ""),
                "story_points": s.get("story_points", ""),
                "timestamp": s["timestamp"], "user_submitted_waf": s["user_submitted_waf"],
                "file_color": s["file_color"], "file_run_change": s["file_run_change"],
                "file_subcategory": s.get("file_subcategory", ""), "file_confidence": s.get("file_confidence", ""),
                "ai_suggested_waf": "", "ai_subcategory": "", "ai_color": "", "ai_run_change": "",
                "ai_confidence": "", "ai_reason": f"API error: {str(e)[:100]}", "is_match": None,
            })
        return results


def _run_verify_job(job_id, stories, filename, ext, row_count,
                    system_prompt=None, waf_version_id=None, gt_version_id=None):
    """Background thread: classify stories using concurrent workers for speed."""
    job = verify_jobs[job_id]

    try:
        if system_prompt is None:
            system_prompt = build_system_prompt()
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        batch_size = int(get_setting("async_batch_size", "50"))
        batches = []
        for i in range(0, len(stories), batch_size):
            batches.append((stories[i:i + batch_size], i))

        total_batches = len(batches)
        job["total_batches"] = total_batches

        # Run up to 5 concurrent API calls for speed
        all_results = [None] * total_batches
        completed = [0]  # mutable counter for thread safety
        lock = threading.Lock()

        def process_batch(batch_idx, batch, offset):
            result = _classify_single_batch(batch, offset, system_prompt, api_key, job_id[:8])
            with lock:
                all_results[batch_idx] = result
                completed[0] += 1
                job["completed_batches"] = completed[0]
                job["stories_processed"] = min(completed[0] * batch_size, len(stories))
                print(f"[BULK-VERIFY][{job_id[:8]}] Batch {completed[0]}/{total_batches} done")
            return result

        with ThreadPoolExecutor(max_workers=int(get_setting("max_concurrent_workers", "5"))) as executor:
            futures = {}
            for idx, (batch, offset) in enumerate(batches):
                f = executor.submit(process_batch, idx, batch, offset)
                futures[f] = idx

            for f in as_completed(futures):
                f.result()  # raise any exceptions

        # Flatten results in order
        results = []
        for batch_result in all_results:
            if batch_result:
                results.extend(batch_result)

        matches = sum(1 for r in results if r["is_match"] is True)
        mismatches = sum(1 for r in results if r["is_match"] is False)
        untagged = sum(1 for r in results if r["is_match"] is None)

        # Record in upload history using a fresh DB connection (we're in a thread)
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.execute(
            """INSERT INTO upload_history
               (uploaded_at, filename, row_count, imported_count, file_type, status, results_json,
                waf_version_id, gt_version_id)
               VALUES (?, ?, ?, ?, ?, 'verified', ?, ?, ?)""",
            (datetime.now().isoformat(), filename, row_count, len(results), ext,
             json.dumps(results), waf_version_id, gt_version_id)
        )
        verify_upload_id = cursor.lastrowid
        db.commit()
        db.close()

        job["status"] = "done"
        job["upload_id"] = verify_upload_id
        job["results"] = results
        job["matches"] = matches
        job["mismatches"] = mismatches
        job["untagged"] = untagged
        print(f"[BULK-VERIFY][{job_id[:8]}] COMPLETE: {len(results)} stories, {matches} matches, {mismatches} mismatches, {untagged} untagged")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        print(f"[BULK-VERIFY][{job_id[:8]}] FATAL ERROR: {str(e)}")


# ── Routes ────────────────────────────────────────────────────────────

@verify_bp.route("/api/bulk-verify/preview", methods=["POST"])
def bulk_verify_preview():
    """Upload a file and return column info for field mapping, without starting AI classification."""
    _cleanup_previews()

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in ("csv", "tsv"):
            df = pd.read_csv(filepath, sep="\t" if ext == "tsv" else ",")
        elif ext in ("xlsx", "xls"):
            df = pd.read_excel(filepath)
        else:
            return jsonify({"error": "File must be CSV or Excel"}), 400

        original_columns = list(df.columns)
        df.columns = [c.strip().lower() for c in df.columns]

        find_col = lambda kws: _find_col(df.columns, kws)

        # Auto-detect suggested mappings
        suggested = {}
        target_fields = [
            {"key": "title", "label": "Story Title", "required": True, "keywords": ["story title", "title", "summary", "story", "name"]},
            {"key": "description", "label": "Story Description", "required": True, "keywords": ["story description", "description", "desc", "detail", "body", "acceptance"]},
            {"key": "waf_category", "label": "WAF Category", "required": False, "keywords": ["waf category", "waf_category", "category"]},
            {"key": "waf_color", "label": "WAF Color", "required": False, "keywords": ["waf color", "waf_color", "color"]},
            {"key": "run_change", "label": "Run/Change", "required": False, "keywords": ["run/change", "run_change", "run change"]},
            {"key": "subcategory", "label": "Sub-Category", "required": False, "keywords": ["sub-category", "sub_category", "subcategory", "waf sub"]},
            {"key": "confidence", "label": "Confidence", "required": False, "keywords": ["confidence", "conf"]},
            {"key": "team", "label": "Team", "required": False, "keywords": ["team", "squad", "group"]},
            {"key": "story_points", "label": "Story Points", "required": False, "keywords": ["story points", "story_points", "points", " sp ", "estimate"]},
            {"key": "epic", "label": "Epic", "required": False, "keywords": ["epic", "initiative", "program"]},
            {"key": "parent_feature", "label": "Parent Feature", "required": False, "keywords": ["feature", "parent feature", "parent_feature", "capability"]},
            {"key": "timestamp", "label": "Timestamp", "required": False, "keywords": ["timestamp", "date", "created", "created_at"]},
            {"key": "story_id", "label": "Story ID", "required": False, "keywords": ["story id", "story_id", "issue key", "issue_key", "ticket", "jira id", "item id"]},
            {"key": "feature_id", "label": "Feature ID", "required": False, "keywords": ["feature id", "feature_id", "feature key", "parent id", "parent_id", "parent key"]},
            {"key": "epic_id", "label": "Epic ID", "required": False, "keywords": ["epic id", "epic_id", "epic key", "epic_key", "epic link", "initiative id"]},
        ]
        for field in target_fields:
            matched = find_col(field["keywords"])
            suggested[field["key"]] = matched or ""

        # Get sample rows
        sample_rows = []
        for _, row in df.head(3).iterrows():
            sample_rows.append({col: str(row.get(col, "")) for col in df.columns})

        preview_id = str(uuid.uuid4())
        _preview_store[preview_id] = {
            "df": df,
            "filename": filename,
            "ext": ext,
            "filepath": filepath,
            "created": _time.time(),
        }

        return jsonify({
            "success": True,
            "filename": filename,
            "file_columns": list(df.columns),
            "original_columns": original_columns,
            "suggested_mappings": suggested,
            "target_fields": [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in target_fields],
            "sample_rows": sample_rows,
            "total_rows": len(df),
            "preview_id": preview_id,
        })
    except Exception as e:
        logger.error("Preview failed: %s", e, exc_info=True)
        return jsonify({"error": f"Failed to parse file: {str(e)[:200]}"}), 500


@verify_bp.route("/api/bulk-verify", methods=["POST"])
def bulk_verify():
    """Upload a file of stories, start async AI classification, return job_id for polling."""
    client_ip = request.remote_addr or "unknown"
    if not _check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded for bulk-verify from %s", client_ip)
        return jsonify({"error": "Too many requests. Please wait a minute before uploading again."}), 429

    # Check if this is a mapped upload (from preview flow)
    preview_id = request.form.get("preview_id", "")
    mappings_json = request.form.get("column_mappings", "")

    if preview_id and preview_id in _preview_store:
        # Use cached DataFrame and user-provided mappings
        preview = _preview_store[preview_id]
        df = preview["df"]
        filename = preview["filename"]
        ext = preview["ext"]
        try:
            mappings = json.loads(mappings_json) if mappings_json else {}
        except (json.JSONDecodeError, TypeError):
            mappings = {}

        title_col = mappings.get("title", "") or None
        desc_col = mappings.get("description", "") or None
        cat_col = mappings.get("waf_category", "") or None
        color_col = mappings.get("waf_color", "") or None
        rc_col = mappings.get("run_change", "") or None
        subcat_col = mappings.get("subcategory", "") or None
        conf_col = mappings.get("confidence", "") or None
        team_col = mappings.get("team", "") or None
        epic_col = mappings.get("epic", "") or None
        feature_col = mappings.get("parent_feature", "") or None
        ts_col = mappings.get("timestamp", "") or None
        story_id_col = mappings.get("story_id", "") or None
        feature_id_col = mappings.get("feature_id", "") or None
        epic_id_col = mappings.get("epic_id", "") or None
        story_points_col = mappings.get("story_points", "") or None

        if not title_col:
            return jsonify({"error": "Title column mapping is required"}), 400

        # Clean up the preview
        del _preview_store[preview_id]
    else:
        # Original flow — upload file and auto-detect columns
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext in ("csv", "tsv"):
                df = pd.read_csv(filepath, sep="\t" if ext == "tsv" else ",")
            elif ext in ("xlsx", "xls"):
                df = pd.read_excel(filepath)
            else:
                return jsonify({"error": "File must be CSV or Excel"}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to read file: {str(e)[:200]}"}), 400

        df.columns = [c.strip().lower() for c in df.columns]
        find_col = lambda kws: _find_col(df.columns, kws)

        title_col = find_col(["story title", "title", "summary", "story", "name"])
        desc_col = find_col(["story description", "description", "desc", "detail", "body", "acceptance"])
        cat_col = find_col(["waf category", "waf_category", "category"])
        color_col = find_col(["waf color", "waf_color", "color"])
        rc_col = find_col(["run/change", "run_change", "run change"])
        subcat_col = find_col(["sub-category", "sub_category", "subcategory", "waf sub"])
        conf_col = find_col(["confidence", "conf"])
        team_col = find_col(["team", "squad", "group"])
        epic_col = find_col(["epic", "initiative", "program"])
        feature_col = find_col(["feature", "parent feature", "parent_feature", "capability"])
        ts_col = find_col(["timestamp", "date", "created", "created_at"])
        story_id_col = find_col(["story id", "story_id", "issue key", "issue_key", "ticket", "jira id", "item id"])
        feature_id_col = find_col(["feature id", "feature_id", "feature key", "parent id", "parent_id", "parent key"])
        epic_id_col = find_col(["epic id", "epic_id", "epic key", "epic_key", "epic link", "initiative id"])
        story_points_col = find_col(["story points", "story_points", "points", " sp ", "estimate"])

        if not title_col:
            return jsonify({"error": "File must have a 'Story Title' or 'Summary' column"}), 400

    # -- Common path: build stories from DataFrame + column mappings --
    try:
        stories = []
        for _, row in df.iterrows():
            title = str(row.get(title_col, "")).strip()
            if not title or title == "nan":
                continue
            ts = datetime.now().isoformat()
            if ts_col:
                raw_ts = str(row.get(ts_col, "")).strip()
                if raw_ts and raw_ts != "nan":
                    ts = raw_ts
            stories.append({
                "title": title,
                "description": str(row.get(desc_col, "")).strip() if desc_col else "",
                "user_submitted_waf": str(row.get(cat_col, "")).strip() if cat_col else "",
                "file_color": str(row.get(color_col, "")).strip() if color_col else "",
                "file_run_change": str(row.get(rc_col, "")).strip() if rc_col else "",
                "file_subcategory": str(row.get(subcat_col, "")).strip() if subcat_col else "",
                "file_confidence": str(row.get(conf_col, "")).strip() if conf_col else "",
                "team": str(row.get(team_col, "default")).strip() if team_col else "default",
                "epic": str(row.get(epic_col, "")).strip() if epic_col else "",
                "parent_feature": str(row.get(feature_col, "")).strip() if feature_col else "",
                "timestamp": ts,
                "story_id": str(row.get(story_id_col, "")).strip() if story_id_col else "",
                "feature_id": str(row.get(feature_id_col, "")).strip() if feature_id_col else "",
                "epic_id": str(row.get(epic_id_col, "")).strip() if epic_id_col else "",
                "story_points": str(row.get(story_points_col, "")).strip() if story_points_col else "",
            })

        if not stories:
            return jsonify({"error": "No valid stories found in file"}), 400

        # Read optional version overrides from the form
        def _to_int_or_none(val):
            try:
                return int(val) if val else None
            except (ValueError, TypeError):
                return None

        waf_version_id = _to_int_or_none(request.form.get("waf_version_id"))
        gt_version_id  = _to_int_or_none(request.form.get("gt_version_id"))

        # Build system prompt now (in the request context) using selected versions
        if waf_version_id or gt_version_id:
            system_prompt = build_system_prompt_for_versions(waf_version_id, gt_version_id)
        else:
            system_prompt = build_system_prompt()

        # All files process asynchronously with progress polling
        job_id = str(uuid.uuid4())
        verify_jobs[job_id] = {
            "status": "processing",
            "total_stories": len(stories),
            "stories_processed": 0,
            "total_batches": 0,
            "completed_batches": 0,
            "current_batch": 0,
            "filename": filename,
            "waf_version_id": waf_version_id,
            "gt_version_id": gt_version_id,
            "results": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }

        thread = threading.Thread(
            target=_run_verify_job,
            args=(job_id, stories, filename, ext, len(df),
                  system_prompt, waf_version_id, gt_version_id),
            daemon=True
        )
        thread.start()

        return jsonify({
            "success": True,
            "async": True,
            "job_id": job_id,
            "total_stories": len(stories),
            "message": f"Processing {len(stories)} stories in background. Poll /api/bulk-verify/status/{job_id} for progress.",
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error("Verification failed: %s", e, exc_info=True)
        return jsonify({"error": "Verification failed. Please try again."}), 500


@verify_bp.route("/api/bulk-verify/status/<job_id>", methods=["GET"])
def bulk_verify_status(job_id):
    """Poll progress of an async bulk-verify job."""
    job = verify_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    resp = {
        "status": job["status"],
        "total_stories": job["total_stories"],
        "stories_processed": job["stories_processed"],
        "total_batches": job["total_batches"],
        "completed_batches": job["completed_batches"],
        "filename": job["filename"],
    }

    if job["status"] == "done":
        resp["success"] = True
        resp["upload_id"] = job.get("upload_id")
        resp["total"] = len(job["results"])
        resp["matches"] = job["matches"]
        resp["mismatches"] = job["mismatches"]
        resp["untagged"] = job["untagged"]
        resp["results"] = job["results"]
        # Clean up after results are fetched
        del verify_jobs[job_id]
    elif job["status"] == "error":
        resp["error"] = job["error"]
        del verify_jobs[job_id]

    return jsonify(resp)


@verify_bp.route("/api/bulk-verify/jobs", methods=["GET"])
def list_verify_jobs():
    """Return all in-memory classification jobs (running + recently completed)."""
    _cleanup_jobs()
    jobs = []
    for jid, job in list(verify_jobs.items()):
        jobs.append({
            "job_id": jid,
            "status": job["status"],
            "filename": job.get("filename", ""),
            "total_stories": job.get("total_stories", 0),
            "stories_processed": job.get("stories_processed", 0),
            "total_batches": job.get("total_batches", 0),
            "completed_batches": job.get("completed_batches", 0),
            "upload_id": job.get("upload_id"),
            "matches": job.get("matches", 0),
            "mismatches": job.get("mismatches", 0),
            "error": job.get("error", ""),
            "started_at": job.get("started_at", ""),
        })
    # Most recent first
    jobs.sort(key=lambda j: j.get("started_at", ""), reverse=True)
    return jsonify({"jobs": jobs})


@verify_bp.route("/api/classifications/<int:classification_id>", methods=["GET"])
def get_classification(classification_id):
    """Return full details for a single classification."""
    db = get_db()
    row = db.execute("SELECT * FROM classifications WHERE id = ?", (classification_id,)).fetchone()
    if not row:
        return jsonify({"error": "Classification not found"}), 404
    return jsonify({k: row[k] for k in row.keys()})


@verify_bp.route("/api/bulk-verify/save", methods=["POST"])
def bulk_verify_save():
    """Save approved rows from bulk verification to the database."""
    data = request.json
    if not data or "rows" not in data:
        return jsonify({"error": "No rows provided"}), 400

    saved = 0
    upload_id = data.get("upload_id")
    db = get_db()
    for row in data["rows"]:
        # Determine which category to use (AI recommendation or file's original)
        use_ai = row.get("use_ai", True)
        category = row.get("ai_suggested_waf", "") if use_ai else row.get("user_submitted_waf", "")
        subcategory = row.get("ai_subcategory", "") if use_ai else row.get("file_subcategory", "")
        color = row.get("ai_color", "") if use_ai else row.get("file_color", "")
        run_change = row.get("ai_run_change", "") if use_ai else row.get("file_run_change", "")
        confidence = row.get("ai_confidence", "") if use_ai else row.get("file_confidence", "")
        ts = row.get("timestamp", datetime.now().isoformat())

        db.execute(
            """INSERT INTO classifications
               (timestamp, story_title, story_description, waf_category,
                waf_subcategory, waf_color, run_change, confidence,
                was_mismatch, original_tag, approved, team, epic, parent_feature,
                story_id, feature_id, epic_id, story_points, upload_id, original_color,
                waf_reasoning)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts,
             row.get("title", ""),
             row.get("description", ""),
             category,
             subcategory,
             color,
             run_change,
             confidence,
             1 if row.get("is_match") is False else 0,  # was_mismatch
             row.get("user_submitted_waf", ""),
             1,  # approved — user explicitly saved this row
             row.get("team", "default"),
             row.get("epic", ""),
             row.get("parent_feature", ""),
             row.get("story_id", ""),
             row.get("feature_id", ""),
             row.get("epic_id", ""),
             row.get("story_points", ""),
             upload_id,
             row.get("file_color", ""),
             row.get("ai_reason", ""))
        )
        saved += 1

    db.commit()
    return jsonify({"success": True, "saved": saved})
