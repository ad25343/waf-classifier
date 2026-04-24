"""
WAF Classifier — Core WAF logic (parsing, normalization, prompt building, AI client).
Extracted from app.py.
"""

import os
import json
import time as _time

import pandas as pd
from anthropic import Anthropic

from config import AI_BACKEND, AI_MODEL, _BEDROCK_AVAILABLE, MAX_BULK_JOBS_PER_MINUTE
from state import (
    waf_store,
    ground_truth_store,
    DEFAULT_WAF_CATEGORIES,
    WAF_ALIASES,
    _rate_limit_store,
)
from database import get_setting

# Conditional import for Bedrock client
try:
    from anthropic import AnthropicBedrock as _AnthropicBedrock
except ImportError:
    _AnthropicBedrock = None


def normalize_waf_category(raw_category, known_categories=None):
    """Normalize a WAF category using exact match, substring, and alias lookup.

    Returns (normalized_category, was_normalized, original_value).
    If ambiguous (multiple substring matches), keeps original and lets AI resolve.
    """
    if not raw_category or str(raw_category).strip().lower() == "nan":
        return ("", False, raw_category or "")

    raw = str(raw_category).strip()
    raw_lower = raw.lower()

    cats = known_categories or waf_store.get("categories") or DEFAULT_WAF_CATEGORIES
    cats = [str(c) for c in cats if c and str(c).strip().lower() != "nan"]

    # 1. Exact match (case-insensitive)
    for cat in cats:
        if raw_lower == cat.lower().strip():
            return (cat, False, raw)

    # 2. Substring containment
    substring_matches = []
    for cat in cats:
        cat_lower = cat.lower().strip()
        if raw_lower in cat_lower or cat_lower in raw_lower:
            substring_matches.append(cat)

    if len(substring_matches) == 1:
        return (substring_matches[0], True, raw)
    # Ambiguous — don't normalize

    # 3. Alias lookup
    if raw_lower in WAF_ALIASES:
        return (WAF_ALIASES[raw_lower], True, raw)

    # 4. Smart KTLO detection — any string containing "ktlo" or
    #    both "keep"+"lights"+"on" normalizes to the canonical form
    if "ktlo" in raw_lower or ("keep" in raw_lower and "lights" in raw_lower and "on" in raw_lower):
        canonical = next((c for c in cats if c.lower().startswith("ktlo")), "KTLO (Keep the Lights On)")
        return (canonical, True, raw)

    # No match — return as-is
    return (raw, False, raw)


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
    """Parse WAF definitions from uploaded file (CSV, Excel, or text).
    Returns (text, categories, df_or_none) — df is the DataFrame if structured, else None."""
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext in ("csv", "tsv"):
        sep = "\t" if ext == "tsv" else ","
        df = pd.read_csv(filepath, sep=sep)
        text = df.to_string(index=False)
        categories = _extract_categories_from_df(df)
        return text, categories, df

    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(filepath)
        text = df.to_string(index=False)
        categories = _extract_categories_from_df(df)
        return text, categories, df

    elif ext in ("txt", "md"):
        with open(filepath, "r") as f:
            text = f.read()
        return text, [], None

    elif ext == "json":
        with open(filepath, "r") as f:
            data = json.load(f)
        text = json.dumps(data, indent=2)
        if isinstance(data, list):
            categories = [item.get("name", item.get("category", "")) for item in data if isinstance(item, dict)]
        return text, categories, None

    else:
        with open(filepath, "r") as f:
            text = f.read()
        return text, [], None


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


def get_client():
    """Return AI client. Uses Anthropic API key if set, otherwise AWS Bedrock."""
    if AI_BACKEND == "anthropic":
        return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    if not _BEDROCK_AVAILABLE:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found and AnthropicBedrock is not installed. "
            "Set ANTHROPIC_API_KEY in .env, or install the anthropic[bedrock] extra."
        )
    aws_region = os.environ.get("AWS_DEFAULT_REGION",
                                os.environ.get("AWS_REGION", "us-east-1"))
    return _AnthropicBedrock(aws_region=aws_region)


def build_ground_truth_section(examples=None, stats=None):
    """Build the ground truth examples section for the system prompt.

    If examples/stats not provided, reads from the global ground_truth_store.
    """
    if examples is None:
        if not ground_truth_store["loaded"] or not ground_truth_store["examples"]:
            return ""
        examples = ground_truth_store["examples"]
        stats = ground_truth_store["stats"]

    if not examples:
        return ""

    section = """

--- GROUND TRUTH: CORRECTLY CLASSIFIED EXAMPLES ---
The following are REAL stories that have been CORRECTLY classified by experienced team members.
Use these as calibration examples to understand how this team applies WAF categories.
When classifying new stories, pattern-match against these examples for consistency.

"""

    # Show distribution
    section += "Category Distribution in Training Data:\n"
    for cat, count in sorted((stats or {}).items(), key=lambda x: -x[1]):
        section += f"  - {cat}: {count} examples\n"
    section += "\n"

    # Show up to 50 examples (or all if fewer), grouped by category
    categories_shown = {}
    max_per_category = max(3, 50 // max(len(stats or {}), 1))

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


def build_system_prompt(waf_raw_text=None, waf_filename=None, waf_categories=None,
                        gt_examples=None, gt_stats=None):
    """Build the system prompt with WAF definitions and ground truth context.

    All parameters are optional. When omitted the global waf_store /
    ground_truth_store values are used (backward-compatible default).
    Pass explicit values to override for a specific classification run
    without mutating global state.
    """
    _waf_raw_text  = waf_raw_text  if waf_raw_text  is not None else waf_store["raw_text"]
    _waf_filename  = waf_filename  if waf_filename  is not None else waf_store.get("filename", "")
    _waf_categories = waf_categories if waf_categories is not None else waf_store["categories"]

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
- **WAF Color:** [use ONLY the exact color from this fixed mapping — do not guess or deviate:
  KTLO (Keep the Lights On) → GRAY
  Business Maintenance → BLACK
  Technical Maintenance → BLACK
  Regulatory (Operational) → RED
  Regulatory Mandated Change → RED
  Enterprise Strategic Priority → ORANGE
  Top Divisional Priority → YELLOW
  Other Block Priority → GREEN]
- **Confidence:** [High/Medium/Low]
- **Reasoning:** [2-3 sentences explaining why, referencing definitions AND similar ground truth examples]
- **Current Tag Assessment:** [only if a current tag was provided — either "\u2705 Correct" or "\u26a0\ufe0f Mismatch — should be [X] instead of [Y]" with explanation]
- **Similar Ground Truth Examples:** [list 1-2 similar examples from ground truth that support your recommendation]
- **Suggestion:** [optional — if the story text is vague, suggest how to improve it]
"""

    if _waf_raw_text:
        base += f"""

--- WAF CATEGORY DEFINITIONS ---
Source file: {_waf_filename}

{_waf_raw_text}

--- END OF WAF DEFINITIONS ---

Use ONLY the categories defined above. Do not invent new categories. If a story doesn't fit any category well, say so and explain why.
"""
        if _waf_categories:
            base += f"\nAvailable categories: {', '.join(str(c) for c in _waf_categories)}\n"
    else:
        base += """

\u26a0\ufe0f No WAF definitions have been uploaded yet. Ask the user to upload their WAF category definitions file so you can provide accurate classifications.
"""

    # Add ground truth section (uses explicit examples/stats when provided)
    gt_section = build_ground_truth_section(examples=gt_examples, stats=gt_stats)
    if gt_section:
        base += gt_section
    else:
        base += """

\u2139\ufe0f No ground truth examples have been uploaded yet. Ground truth examples (correctly classified stories) improve classification accuracy significantly. Suggest the user upload them if available.
"""

    return base


def build_system_prompt_for_versions(waf_version_id=None, gt_version_id=None):
    """Build a system prompt using specific named version IDs.

    Loads WAF definitions and/or ground truth from their saved version files
    without touching global state. Falls back to global store for any version
    ID that is None or cannot be resolved.
    """
    import sqlite3 as _sqlite3
    from config import DB_PATH as _DB_PATH

    waf_raw_text = waf_filename = waf_categories = gt_examples = gt_stats = None

    if waf_version_id:
        try:
            conn = _sqlite3.connect(_DB_PATH)
            conn.row_factory = _sqlite3.Row
            row = conn.execute(
                "SELECT * FROM waf_versions WHERE id=?", (waf_version_id,)
            ).fetchone()
            conn.close()
            if row and os.path.exists(row["filepath"]):
                text, cats, _df = parse_waf_file(row["filepath"], row["filename"])
                waf_raw_text   = text
                waf_filename   = row["name"]   # show human name in the prompt
                waf_categories = cats
                print(f"[VERSIONS] Using WAF version '{row['name']}' (id={waf_version_id})")
        except Exception as e:
            print(f"[VERSIONS] Could not load WAF version {waf_version_id}: {e} — falling back to active store")

    if gt_version_id:
        try:
            conn = _sqlite3.connect(_DB_PATH)
            conn.row_factory = _sqlite3.Row
            row = conn.execute(
                "SELECT * FROM gt_versions WHERE id=?", (gt_version_id,)
            ).fetchone()
            conn.close()
            if row and os.path.exists(row["filepath"]):
                examples, stats, _ = parse_ground_truth(row["filepath"], row["filename"])
                gt_examples = examples
                gt_stats    = stats
                print(f"[VERSIONS] Using GT version '{row['name']}' (id={gt_version_id})")
        except Exception as e:
            print(f"[VERSIONS] Could not load GT version {gt_version_id}: {e} — falling back to active store")

    return build_system_prompt(
        waf_raw_text=waf_raw_text,
        waf_filename=waf_filename,
        waf_categories=waf_categories,
        gt_examples=gt_examples,
        gt_stats=gt_stats,
    )


def _check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate limit exceeded."""
    now = _time.time()
    limit = int(get_setting("rate_limit_per_minute", str(MAX_BULK_JOBS_PER_MINUTE)))
    hits = [t for t in _rate_limit_store.get(ip, []) if now - t < 60]
    if len(hits) >= limit:
        return False
    hits.append(now)
    _rate_limit_store[ip] = hits
    return True
