"""
WAF Classifier — Classification routes.
Handles file uploads, AI classification, and state management.
"""

import os
import re
import csv
import logging

from flask import Blueprint, request, jsonify, g
from werkzeug.utils import secure_filename

from state import waf_store, ground_truth_store, chat_history
from config import AI_MODEL, UPLOAD_FOLDER
from database import get_db, save_classification, get_setting, set_setting
from waf_core import parse_waf_file, parse_ground_truth, get_client, build_system_prompt, build_system_prompt_for_versions

logger = logging.getLogger(__name__)

classify_bp = Blueprint("classify_bp", __name__)


@classify_bp.route("/api/upload-waf", methods=["POST"])
def upload_waf():
    """Upload WAF definitions file."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        text, categories, df = parse_waf_file(filepath, filename)
        waf_store["definitions"] = df
        waf_store["raw_text"] = text
        waf_store["filename"] = filename
        waf_store["categories"] = categories
        set_setting("active_waf_path", filepath)

        return jsonify({
            "success": True,
            "filename": filename,
            "categories": [str(c) for c in categories],
            "preview": text[:500] + ("..." if len(text) > 500 else "")
        })
    except Exception as e:
        logger.error("Failed to parse file: %s", e, exc_info=True)
        return jsonify({"error": "Failed to parse file. Check the format and try again."}), 400


@classify_bp.route("/api/upload-ground-truth", methods=["POST"])
def upload_ground_truth():
    """Upload ground truth file with correctly classified stories."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        examples, stats, col_map = parse_ground_truth(filepath, filename)

        ground_truth_store["loaded"] = True
        ground_truth_store["filename"] = filename
        ground_truth_store["examples"] = examples
        ground_truth_store["example_count"] = len(examples)
        ground_truth_store["stats"] = stats
        ground_truth_store["raw_text"] = f"{len(examples)} examples across {len(stats)} categories"
        set_setting("active_gt_path", filepath)

        return jsonify({
            "success": True,
            "filename": filename,
            "example_count": len(examples),
            "stats": stats,
            "columns_detected": {k: v for k, v in col_map.items() if v},
            "sample": examples[:3] if examples else []
        })
    except Exception as e:
        logger.error("Failed to parse ground truth: %s", e, exc_info=True)
        return jsonify({"error": "Failed to parse ground truth file."}), 400


@classify_bp.route("/api/classify", methods=["POST"])
def classify():
    """Classify a JIRA story into a WAF category."""
    data = request.json
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"]
    epic = data.get("epic", "")
    parent_feature = data.get("parent_feature", "")
    story_id = data.get("story_id", "")
    story_points = str(data.get("story_points", "")).strip()
    pi_number = str(data.get("pi_number", "")).strip()

    # Optional version overrides — use a specific WAF/GT version for this call only
    def _to_int_or_none(val):
        try:
            return int(val) if val else None
        except (ValueError, TypeError):
            return None

    waf_version_id = _to_int_or_none(data.get("waf_version_id"))
    gt_version_id  = _to_int_or_none(data.get("gt_version_id"))

    # Prepend epic/feature context to the message so the model has strategic framing
    context_parts = []
    if epic:
        context_parts.append(f"Epic: {epic}")
    if parent_feature:
        context_parts.append(f"Feature: {parent_feature}")
    if context_parts:
        user_message = "[Context — " + " | ".join(context_parts) + "]\n\n" + user_message

    chat_history.append({"role": "user", "content": user_message})
    recent_history = chat_history[-20:]

    if waf_version_id or gt_version_id:
        system = build_system_prompt_for_versions(waf_version_id, gt_version_id)
    else:
        system = build_system_prompt()

    try:
        client = get_client()
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=2000,
            system=system,
            messages=recent_history
        )
        try:
            from routes.usage import record_token_use
            u = getattr(response, "usage", None)
            if u:
                record_token_use(AI_MODEL, getattr(u, "input_tokens", 0) or 0,
                                 getattr(u, "output_tokens", 0) or 0,
                                 route="/api/classify")
        except Exception:
            pass

        assistant_message = response.content[0].text
        chat_history.append({"role": "assistant", "content": assistant_message})

        return jsonify({
            "response": assistant_message,
            "waf_loaded": waf_store["definitions"] is not None or bool(waf_store["raw_text"]),
            "ground_truth_loaded": ground_truth_store["loaded"]
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        logger.error("Classification failed: %s", e, exc_info=True)
        return jsonify({"error": "Classification failed. Please try again."}), 500


@classify_bp.route("/api/batch-classify", methods=["POST"])
def batch_classify():
    """Classify multiple stories from a pasted batch."""
    data = request.json
    stories = data.get("stories", [])

    if not stories:
        return jsonify({"error": "No stories provided"}), 400

    if not waf_store["definitions"]:
        return jsonify({"error": "Please upload WAF definitions first"}), 400

    batch_prompt = "Please classify each of the following JIRA stories into the appropriate WAF category and Team of Teams. For each story, provide the recommended category, Team of Teams, WAF color, confidence level, and brief reasoning. Reference ground truth examples where applicable.\n\n"

    for i, story in enumerate(stories, 1):
        batch_prompt += f"**Story {i}:**\n"
        batch_prompt += f"- Title: {story.get('title', 'N/A')}\n"
        if story.get("description"):
            batch_prompt += f"- Description: {story['description']}\n"
        if story.get("current_waf"):
            batch_prompt += f"- Current WAF Tag: {story['current_waf']}\n"
        batch_prompt += "\n"

    batch_prompt += "Provide a summary table at the end showing all stories with their recommended categories, sub-categories, colors, and any mismatches flagged."

    try:
        client = get_client()
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=4000,
            system=build_system_prompt(),
            messages=[{"role": "user", "content": batch_prompt}]
        )
        try:
            from routes.usage import record_token_use
            u = getattr(response, "usage", None)
            if u:
                record_token_use(AI_MODEL, getattr(u, "input_tokens", 0) or 0,
                                 getattr(u, "output_tokens", 0) or 0,
                                 route="/api/batch-classify")
        except Exception:
            pass

        return jsonify({
            "response": response.content[0].text,
            "story_count": len(stories)
        })
    except Exception as e:
        logger.error("Batch classification failed: %s", e, exc_info=True)
        return jsonify({"error": "Batch classification failed. Please try again."}), 500


@classify_bp.route("/api/status", methods=["GET"])
def status():
    """Check current status of the classifier."""
    from config import AI_BACKEND
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({
        "api_key_configured": api_key_set,
        "ai_backend": AI_BACKEND,
        "ai_model": AI_MODEL,
        "waf_loaded": waf_store["definitions"] is not None or bool(waf_store["raw_text"]),
        "waf_filename": waf_store["filename"],
        "waf_categories": [str(c) for c in waf_store["categories"]],
        "ground_truth_loaded": ground_truth_store["loaded"],
        "ground_truth_filename": ground_truth_store["filename"],
        "ground_truth_count": ground_truth_store["example_count"],
        "ground_truth_stats": ground_truth_store["stats"],
        "chat_history_length": len(chat_history)
    })


@classify_bp.route("/api/clear-chat", methods=["POST"])
def clear_chat():
    """Clear chat history."""
    chat_history.clear()
    return jsonify({"success": True})


@classify_bp.route("/api/clear-waf", methods=["POST"])
def clear_waf():
    """Clear uploaded WAF definitions."""
    waf_store["definitions"] = None
    waf_store["raw_text"] = ""
    waf_store["filename"] = ""
    waf_store["categories"] = []
    return jsonify({"success": True})


@classify_bp.route("/api/clear-ground-truth", methods=["POST"])
def clear_ground_truth():
    """Clear uploaded ground truth."""
    ground_truth_store["loaded"] = False
    ground_truth_store["filename"] = ""
    ground_truth_store["examples"] = []
    ground_truth_store["example_count"] = 0
    ground_truth_store["raw_text"] = ""
    ground_truth_store["stats"] = {}
    return jsonify({"success": True})


@classify_bp.route("/api/approve-classification", methods=["POST"])
def approve_classification():
    """Save an approved classification to the ground truth CSV and in-memory store."""
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    run_change = data.get("run_change", "").strip()
    waf_color = data.get("waf_color", "").strip()
    waf_category = data.get("waf_category", "").strip()
    team_of_teams = data.get("team_of_teams", "").strip()

    if not title or not waf_category:
        return jsonify({"error": "Title and WAF Category are required"}), 400

    # 1. Append to the ground truth CSV file
    sample_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample-data")
    gt_file = os.path.join(sample_dir, "sample-ground-truth.csv")

    row = [title, description, run_change, waf_color, waf_category, team_of_teams]
    file_exists = os.path.exists(gt_file)

    try:
        with open(gt_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Story Title", "Description", "Run/Change",
                                 "WAF Color", "WAF Category", "Team of Teams"])
            writer.writerow(row)
    except Exception as e:
        logger.error("Failed to write ground truth: %s", e, exc_info=True)
        return jsonify({"error": "Failed to save ground truth data."}), 500

    # 2. Add to in-memory store
    example = {
        "title": title,
        "description": description,
        "waf_category": waf_category,
        "team_of_teams": team_of_teams,
        "waf_color": waf_color,
    }
    ground_truth_store["examples"].append(example)
    ground_truth_store["example_count"] = len(ground_truth_store["examples"])
    ground_truth_store["loaded"] = True
    if not ground_truth_store["filename"]:
        ground_truth_store["filename"] = "sample-ground-truth.csv"

    # Update stats
    cat = waf_category
    ground_truth_store["stats"][cat] = ground_truth_store["stats"].get(cat, 0) + 1
    ground_truth_store["raw_text"] = (
        f"{ground_truth_store['example_count']} examples across "
        f"{len(ground_truth_store['stats'])} categories"
    )

    # 3. Save to database as approved
    try:
        save_classification(title, description, waf_category, team_of_teams,
                            waf_color, run_change, "HIGH", approved=True)
    except Exception:
        pass  # DB save is best-effort, don't fail the request

    return jsonify({
        "success": True,
        "example_count": ground_truth_store["example_count"],
        "stats": ground_truth_store["stats"],
        "message": f"Saved to ground truth: {title} \u2192 {waf_category}"
    })
