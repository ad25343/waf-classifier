"""
WAF Category Classifier - Backend
Helps scrum teams correctly classify JIRA stories into WAF categories
using Claude AI for intelligent recommendation and mismatch detection.
Supports ground truth examples for calibration.
"""

import os
import json
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from anthropic import Anthropic
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload
app.secret_key = os.urandom(24)

# In-memory store for WAF definitions
waf_store = {
    "definitions": None,
    "raw_text": "",
    "filename": "",
    "categories": []
}

# In-memory store for ground truth examples
ground_truth_store = {
    "loaded": False,
    "filename": "",
    "examples": [],       # list of dicts with story details + correct WAF
    "example_count": 0,
    "raw_text": "",
    "stats": {}           # category distribution stats
}

# Chat history for context
chat_history = []

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_client():
    """Get Anthropic client - requires ANTHROPIC_API_KEY env var."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
    return Anthropic(api_key=api_key)


def _extract_categories_from_df(df):
    """Extract WAF category names from a DataFrame using smart column detection.
    Prioritizes 'category' columns over 'color' or generic 'waf' columns."""
    categories = []
    # Priority 1: Column explicitly named "category" (e.g., "WAF Category")
    for col in df.columns:
        cl = col.lower()
        if "category" in cl and "sub" not in cl:
            categories = df[col].dropna().unique().tolist()
            return categories
    # Priority 2: Column with "name", "type", or "bucket"
    for col in df.columns:
        cl = col.lower()
        if any(kw in cl for kw in ["name", "type", "bucket"]) and "color" not in cl:
            categories = df[col].dropna().unique().tolist()
            return categories
    # Priority 3: Column with "waf" but not "color" or "sub"
    for col in df.columns:
        cl = col.lower()
        if "waf" in cl and "color" not in cl and "sub" not in cl:
            categories = df[col].dropna().unique().tolist()
            return categories
    # Fallback: first column
    if len(df.columns) >= 1:
        categories = df.iloc[:, 0].dropna().unique().tolist()
    return categories


def parse_waf_file(filepath, filename):
    """Parse WAF definitions from uploaded file (CSV, Excel, or text)."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext in ("csv", "tsv"):
        sep = "\t" if ext == "tsv" else ","
        df = pd.read_csv(filepath, sep=sep)
        text = df.to_string(index=False)
        categories = _extract_categories_from_df(df)
        return text, categories

    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(filepath)
        text = df.to_string(index=False)
        categories = _extract_categories_from_df(df)
        return text, categories

    elif ext in ("txt", "md"):
        with open(filepath, "r") as f:
            text = f.read()
        return text, []

    elif ext == "json":
        with open(filepath, "r") as f:
            data = json.load(f)
        text = json.dumps(data, indent=2)
        if isinstance(data, list):
            categories = [item.get("name", item.get("category", "")) for item in data if isinstance(item, dict)]
        return text, categories

    else:
        with open(filepath, "r") as f:
            text = f.read()
        return text, []


def parse_ground_truth(filepath, filename):
    """Parse ground truth file containing correctly classified stories."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext in ("csv", "tsv"):
        sep = "\t" if ext == "tsv" else ","
        df = pd.read_csv(filepath, sep=sep)
    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Ground truth must be CSV or Excel, got .{ext}")

    # Normalize column names (lowercase, strip whitespace)
    df.columns = [c.strip().lower() for c in df.columns]

    # Try to map columns intelligently
    col_map = {
        "title": None,
        "description": None,
        "waf_category": None,
        "waf_subcategory": None,
        "waf_color": None,
    }

    for col in df.columns:
        cl = col.lower()
        if any(kw in cl for kw in ["title", "summary", "story name", "story title", "name"]) and not col_map["title"]:
            col_map["title"] = col
        elif any(kw in cl for kw in ["desc", "detail", "acceptance", "body"]) and not col_map["description"]:
            col_map["description"] = col
        elif any(kw in cl for kw in ["sub-category", "subcategory", "sub category", "sub_cat"]) and not col_map["waf_subcategory"]:
            col_map["waf_subcategory"] = col
        elif any(kw in cl for kw in ["category", "waf cat", "waf_cat", "waf category"]) and not col_map["waf_category"]:
            col_map["waf_category"] = col
        elif any(kw in cl for kw in ["color", "colour", "waf color"]) and not col_map["waf_color"]:
            col_map["waf_color"] = col

    # Build examples list
    examples = []
    for _, row in df.iterrows():
        example = {}
        for key, col in col_map.items():
            if col and col in df.columns:
                val = row.get(col, "")
                example[key] = str(val) if pd.notna(val) else ""
            else:
                example[key] = ""
        # Only include if we have at least a title and category
        if example.get("title") and example.get("waf_category"):
            examples.append(example)

    # Compute stats
    stats = {}
    for ex in examples:
        cat = ex.get("waf_category", "Unknown")
        stats[cat] = stats.get(cat, 0) + 1

    return examples, stats, col_map


def build_ground_truth_section():
    """Build the ground truth examples section for the system prompt."""
    if not ground_truth_store["loaded"] or not ground_truth_store["examples"]:
        return ""

    examples = ground_truth_store["examples"]
    stats = ground_truth_store["stats"]

    section = """

--- GROUND TRUTH: CORRECTLY CLASSIFIED EXAMPLES ---
The following are REAL stories that have been CORRECTLY classified by experienced team members.
Use these as calibration examples to understand how this team applies WAF categories.
When classifying new stories, pattern-match against these examples for consistency.

"""

    # Show distribution
    section += "Category Distribution in Training Data:\n"
    for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
        section += f"  - {cat}: {count} examples\n"
    section += "\n"

    # Show up to 50 examples (or all if fewer), grouped by category
    categories_shown = {}
    max_per_category = max(3, 50 // max(len(stats), 1))

    for ex in examples:
        cat = ex.get("waf_category", "Unknown")
        if cat not in categories_shown:
            categories_shown[cat] = 0

        if categories_shown[cat] >= max_per_category:
            continue

        categories_shown[cat] += 1
        section += f"EXAMPLE — Category: {cat}"
        if ex.get("waf_subcategory"):
            section += f" | Sub-category: {ex['waf_subcategory']}"
        if ex.get("waf_color"):
            section += f" | Color: {ex['waf_color']}"
        section += "\n"
        section += f"  Title: {ex.get('title', 'N/A')}\n"
        if ex.get("description"):
            desc = ex["description"][:300]
            section += f"  Description: {desc}\n"
        section += "\n"

    section += f"--- END OF GROUND TRUTH ({len(examples)} total examples) ---\n"

    return section


def build_system_prompt():
    """Build the system prompt with WAF definitions and ground truth context."""
    base = """You are a WAF (Work Alignment Framework) Classification Expert. Your job is to help agile teams correctly classify their JIRA stories/features into the right WAF category.

You are precise, consistent, and always explain your reasoning by referencing the WAF definitions AND ground truth examples when available.

When classifying a story:
1. Analyze the story title and description carefully
2. Match it against the WAF category definitions provided
3. Cross-reference with ground truth examples to see how similar stories were classified
4. Recommend the BEST-FIT WAF category AND sub-category with clear reasoning
5. If the user provides the current WAF tag, compare it to your recommendation and flag if it's a mismatch
6. Rate your confidence (High / Medium / Low)
7. If the story is ambiguous, explain what additional context would help

Format your response clearly with:
- **Recommended WAF Category:** [category name]
- **Recommended WAF Sub-Category:** [sub-category name, if applicable]
- **WAF Color:** [color, if known from definitions]
- **Confidence:** [High/Medium/Low]
- **Reasoning:** [2-3 sentences explaining why, referencing definitions AND similar ground truth examples]
- **Current Tag Assessment:** [only if a current tag was provided — either "✅ Correct" or "⚠️ Mismatch — should be [X] instead of [Y]" with explanation]
- **Similar Ground Truth Examples:** [list 1-2 similar examples from ground truth that support your recommendation]
- **Suggestion:** [optional — if the story text is vague, suggest how to improve it]
"""

    if waf_store["raw_text"]:
        base += f"""

--- WAF CATEGORY DEFINITIONS ---
Source file: {waf_store['filename']}

{waf_store['raw_text']}

--- END OF WAF DEFINITIONS ---

Use ONLY the categories defined above. Do not invent new categories. If a story doesn't fit any category well, say so and explain why.
"""
        if waf_store["categories"]:
            base += f"\nAvailable categories: {', '.join(str(c) for c in waf_store['categories'])}\n"
    else:
        base += """

⚠️ No WAF definitions have been uploaded yet. Ask the user to upload their WAF category definitions file so you can provide accurate classifications.
"""

    # Add ground truth section
    gt_section = build_ground_truth_section()
    if gt_section:
        base += gt_section
    else:
        base += """

ℹ️ No ground truth examples have been uploaded yet. Ground truth examples (correctly classified stories) improve classification accuracy significantly. Suggest the user upload them if available.
"""

    return base


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/upload-waf", methods=["POST"])
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
        text, categories = parse_waf_file(filepath, filename)
        waf_store["definitions"] = True
        waf_store["raw_text"] = text
        waf_store["filename"] = filename
        waf_store["categories"] = categories

        return jsonify({
            "success": True,
            "filename": filename,
            "categories": [str(c) for c in categories],
            "preview": text[:500] + ("..." if len(text) > 500 else "")
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 400


@app.route("/api/upload-ground-truth", methods=["POST"])
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

        # Build a readable text version for the raw store
        ground_truth_store["raw_text"] = f"{len(examples)} examples across {len(stats)} categories"

        return jsonify({
            "success": True,
            "filename": filename,
            "example_count": len(examples),
            "stats": stats,
            "columns_detected": {k: v for k, v in col_map.items() if v},
            "sample": examples[:3] if examples else []
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse ground truth: {str(e)}"}), 400


@app.route("/api/classify", methods=["POST"])
def classify():
    """Classify a JIRA story into a WAF category."""
    data = request.json
    if not data or not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    user_message = data["message"]
    chat_history.append({"role": "user", "content": user_message})
    recent_history = chat_history[-20:]

    try:
        client = get_client()
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=build_system_prompt(),
            messages=recent_history
        )

        assistant_message = response.content[0].text
        chat_history.append({"role": "assistant", "content": assistant_message})

        return jsonify({
            "response": assistant_message,
            "waf_loaded": waf_store["definitions"] is not None,
            "ground_truth_loaded": ground_truth_store["loaded"]
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Classification failed: {str(e)}"}), 500


@app.route("/api/batch-classify", methods=["POST"])
def batch_classify():
    """Classify multiple stories from a pasted batch."""
    data = request.json
    stories = data.get("stories", [])

    if not stories:
        return jsonify({"error": "No stories provided"}), 400

    if not waf_store["definitions"]:
        return jsonify({"error": "Please upload WAF definitions first"}), 400

    batch_prompt = "Please classify each of the following JIRA stories into the appropriate WAF category and sub-category. For each story, provide the recommended category, sub-category, WAF color, confidence level, and brief reasoning. Reference ground truth examples where applicable.\n\n"

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
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            system=build_system_prompt(),
            messages=[{"role": "user", "content": batch_prompt}]
        )

        return jsonify({
            "response": response.content[0].text,
            "story_count": len(stories)
        })
    except Exception as e:
        return jsonify({"error": f"Batch classification failed: {str(e)}"}), 500


@app.route("/api/status", methods=["GET"])
def status():
    """Check current status of the classifier."""
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return jsonify({
        "api_key_configured": api_key_set,
        "waf_loaded": waf_store["definitions"] is not None,
        "waf_filename": waf_store["filename"],
        "waf_categories": [str(c) for c in waf_store["categories"]],
        "ground_truth_loaded": ground_truth_store["loaded"],
        "ground_truth_filename": ground_truth_store["filename"],
        "ground_truth_count": ground_truth_store["example_count"],
        "ground_truth_stats": ground_truth_store["stats"],
        "chat_history_length": len(chat_history)
    })


@app.route("/api/clear-chat", methods=["POST"])
def clear_chat():
    """Clear chat history."""
    chat_history.clear()
    return jsonify({"success": True})


@app.route("/api/clear-waf", methods=["POST"])
def clear_waf():
    """Clear uploaded WAF definitions."""
    waf_store["definitions"] = None
    waf_store["raw_text"] = ""
    waf_store["filename"] = ""
    waf_store["categories"] = []
    return jsonify({"success": True})


@app.route("/api/clear-ground-truth", methods=["POST"])
def clear_ground_truth():
    """Clear uploaded ground truth."""
    ground_truth_store["loaded"] = False
    ground_truth_store["filename"] = ""
    ground_truth_store["examples"] = []
    ground_truth_store["example_count"] = 0
    ground_truth_store["raw_text"] = ""
    ground_truth_store["stats"] = {}
    return jsonify({"success": True})


@app.route("/api/approve-classification", methods=["POST"])
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
    waf_subcategory = data.get("waf_subcategory", "").strip()

    if not title or not waf_category:
        return jsonify({"error": "Title and WAF Category are required"}), 400

    # 1. Append to the ground truth CSV file
    sample_dir = os.path.join(os.path.dirname(__file__), "sample-data")
    gt_file = os.path.join(sample_dir, "sample-ground-truth.csv")

    row = [title, description, run_change, waf_color, waf_category, waf_subcategory]
    file_exists = os.path.exists(gt_file)

    try:
        import csv
        with open(gt_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Story Title", "Description", "Run/Change",
                                 "WAF Color", "WAF Category", "WAF Sub-Category"])
            writer.writerow(row)
    except Exception as e:
        return jsonify({"error": f"Failed to write to ground truth file: {str(e)}"}), 500

    # 2. Add to in-memory store
    example = {
        "title": title,
        "description": description,
        "waf_category": waf_category,
        "waf_subcategory": waf_subcategory,
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

    return jsonify({
        "success": True,
        "example_count": ground_truth_store["example_count"],
        "stats": ground_truth_store["stats"],
        "message": f"Saved to ground truth: {title} → {waf_category}"
    })


def auto_load_sample_data():
    """Auto-load WAF definitions and ground truth from sample-data/ on startup."""
    sample_dir = os.path.join(os.path.dirname(__file__), "sample-data")

    # Load WAF definitions
    waf_file = os.path.join(sample_dir, "waf-definitions.csv")
    if os.path.exists(waf_file):
        try:
            text, categories = parse_waf_file(waf_file, "waf-definitions.csv")
            waf_store["definitions"] = True
            waf_store["raw_text"] = text
            waf_store["filename"] = "waf-definitions.csv"
            waf_store["categories"] = categories
            print(f"  Auto-loaded WAF definitions: {len(categories)} categories")
        except Exception as e:
            print(f"  Warning: Failed to auto-load WAF definitions: {e}")

    # Load ground truth
    gt_file = os.path.join(sample_dir, "sample-ground-truth.csv")
    if os.path.exists(gt_file):
        try:
            examples, stats, col_map = parse_ground_truth(gt_file, "sample-ground-truth.csv")
            ground_truth_store["loaded"] = True
            ground_truth_store["filename"] = "sample-ground-truth.csv"
            ground_truth_store["examples"] = examples
            ground_truth_store["example_count"] = len(examples)
            ground_truth_store["stats"] = stats
            ground_truth_store["raw_text"] = f"{len(examples)} examples across {len(stats)} categories"
            print(f"  Auto-loaded ground truth: {len(examples)} examples across {len(stats)} categories")
        except Exception as e:
            print(f"  Warning: Failed to auto-load ground truth: {e}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n{'='*60}")
    print(f"  WAF Category Classifier")
    print(f"  Running at: http://localhost:{port}")
    print(f"  API Key configured: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    auto_load_sample_data()
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=True)
