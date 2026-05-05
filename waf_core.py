"""
WAF Classifier — Core WAF logic (parsing, normalization, prompt building, AI client).
Extracted from app.py.
"""

import os
import re
import json
import time as _time

import pandas as pd
from anthropic import Anthropic

from config import (
    AI_BACKEND, AI_MODEL, _BEDROCK_AVAILABLE, MAX_BULK_JOBS_PER_MINUTE,
    PORTKEY_API_KEY, PORTKEY_VIRTUAL_KEY, PORTKEY_GATEWAY_URL,
    APIGEE_GATEWAY_URL, APIGEE_TOKEN_URL, APIGEE_CLIENT_ID,
    APIGEE_CLIENT_SECRET, APIGEE_EXTRA_HEADERS,
)
from state import (
    waf_store,
    ground_truth_store,
    DEFAULT_WAF_CATEGORIES,
    WAF_ALIASES,
    _rate_limit_store,
)
from database import get_setting, get_all_aliases_dict

# Conditional import for Bedrock client
try:
    from anthropic import AnthropicBedrock as _AnthropicBedrock
except ImportError:
    _AnthropicBedrock = None


# ── Alias cache (invalidated on add/delete via routes/aliases.py) ─────
_ALIAS_CACHE = {"data": None}

def invalidate_alias_cache():
    """Drop the alias cache so the next lookup re-reads from the DB."""
    _ALIAS_CACHE["data"] = None

def _all_aliases():
    """DB aliases merged over the WAF_ALIASES seed dict.
    Cached at module level; call invalidate_alias_cache() after writes."""
    if _ALIAS_CACHE["data"] is None:
        merged = dict(WAF_ALIASES)
        merged.update(get_all_aliases_dict())
        _ALIAS_CACHE["data"] = merged
    return _ALIAS_CACHE["data"]


_PUNCT_RE = re.compile(r"[()\[\]\-_:.,/]")
_WS_RE    = re.compile(r"\s+")

def _strip_punct(s):
    """Lower + replace punctuation with spaces + collapse whitespace.
    Used for fuzzy compare so 'Reg. Operational' ≈ 'Regulatory (Operational)'.
    Also strips a final 's' on each word so plural/singular drift folds together
    ('Regulatory Operations' ≈ 'Regulatory Operational' both → 'regulatory operation').
    NOTE: 'Operational' loses its 'al' suffix here too — handled by the suffix
    rule below."""
    if s is None:
        return ""
    t = _WS_RE.sub(" ", _PUNCT_RE.sub(" ", str(s).lower())).strip()
    # Fold simple morphology: drop trailing 's' and 'al' on each token so
    # Operations/Operational/Operation all collapse to 'operation'.
    out = []
    for tok in t.split(" "):
        if not tok:
            continue
        if len(tok) > 4 and tok.endswith("al"):
            tok = tok[:-2]
        if len(tok) > 3 and tok.endswith("s"):
            tok = tok[:-1]
        out.append(tok)
    return " ".join(out)


def normalize_waf_category(raw_category, known_categories=None):
    """Normalize a WAF category using exact match, punctuation/morphology
    fold, substring containment, alias lookup (DB + dict), and a smart
    KTLO heuristic.

    Returns (normalized_category, was_normalized, original_value).
    If ambiguous (multiple substring matches), keeps original and lets AI resolve.
    """
    if not raw_category or str(raw_category).strip().lower() == "nan":
        return ("", False, raw_category or "")

    raw = str(raw_category).strip()
    raw_lower = raw.lower()
    raw_stripped = _strip_punct(raw)

    cats = known_categories or waf_store.get("categories") or DEFAULT_WAF_CATEGORIES
    cats = [str(c) for c in cats if c and str(c).strip().lower() != "nan"]

    # 1. Exact match (case-insensitive)
    for cat in cats:
        if raw_lower == cat.lower().strip():
            return (cat, False, raw)

    # 2. Punctuation- and morphology-stripped exact match
    #    Catches: "Reg. Operational" vs "Regulatory (Operational)",
    #             "Regulatory (Operations)" vs "Regulatory (Operational)"
    for cat in cats:
        if raw_stripped and raw_stripped == _strip_punct(cat):
            return (cat, True, raw)

    # 3. Substring containment (using stripped forms for robustness)
    substring_matches = []
    for cat in cats:
        cs = _strip_punct(cat)
        if raw_stripped and cs and (raw_stripped in cs or cs in raw_stripped):
            substring_matches.append(cat)
    if len(substring_matches) == 1:
        return (substring_matches[0], True, raw)
    # Ambiguous — don't normalize via substring

    # 4. Alias lookup (DB + dict). Try exact key, then stripped form.
    aliases = _all_aliases()
    if raw_lower in aliases:
        return (aliases[raw_lower], True, raw)
    for k, v in aliases.items():
        if _strip_punct(k) == raw_stripped:
            return (v, True, raw)

    # 5. Smart KTLO detection — any string containing "ktlo" or
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
        "team_of_teams": None,
        "waf_color": None,
    }

    for col in df.columns:
        cl = col.lower()
        if any(kw in cl for kw in ["title", "summary", "story name", "story title", "name"]) and not col_map["title"]:
            col_map["title"] = col
        elif any(kw in cl for kw in ["desc", "detail", "acceptance", "body"]) and not col_map["description"]:
            col_map["description"] = col
        # Team of Teams: strict match only. Do NOT add subcategory fallbacks —
        # they were leftovers from when this column was named waf_subcategory,
        # and they cause unrelated columns to silently land in team_of_teams.
        elif any(kw in cl for kw in ["team of teams", "team_of_teams"]) and not col_map["team_of_teams"]:
            col_map["team_of_teams"] = col
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
    """Return an AI client based on AI_BACKEND / AI_GATEWAY configuration.

    Supported backends (set via .env):
      anthropic  — direct Anthropic API          (ANTHROPIC_API_KEY)
      bedrock    — AWS Bedrock (direct)           (AWS credentials)
      portkey    — PortKey AI gateway             (PORTKEY_API_KEY + PORTKEY_VIRTUAL_KEY)
      apigee     — Apigee gateway → Bedrock       (APIGEE_* credentials)
    """
    if AI_BACKEND == "anthropic":
        return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    if AI_BACKEND == "portkey":
        return _get_portkey_client()

    if AI_BACKEND == "apigee":
        return _get_apigee_client()

    # Default: direct Bedrock
    if not _BEDROCK_AVAILABLE:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found and AnthropicBedrock is not installed. "
            "Set ANTHROPIC_API_KEY in .env, or install the anthropic[bedrock] extra."
        )
    aws_region = os.environ.get("AWS_DEFAULT_REGION",
                                os.environ.get("AWS_REGION", "us-east-1"))
    return _AnthropicBedrock(aws_region=aws_region)


def _get_portkey_client():
    """Build an Anthropic client that routes through the PortKey AI gateway.

    PortKey exposes an Anthropic-compatible endpoint.  The SDK just needs a
    custom base_url and the PortKey auth headers.

    Install: pip install portkey-ai
    Docs:    https://portkey.ai/docs/integrations/llms/anthropic
    """
    if not PORTKEY_API_KEY:
        raise RuntimeError(
            "AI_GATEWAY=portkey requires PORTKEY_API_KEY in .env"
        )
    headers = {
        "x-portkey-api-key": PORTKEY_API_KEY,
    }
    if PORTKEY_VIRTUAL_KEY:
        headers["x-portkey-virtual-key"] = PORTKEY_VIRTUAL_KEY

    # Try the official portkey-ai SDK helper first; fall back to raw headers
    try:
        from portkey_ai import createHeaders
        pk_headers = createHeaders(
            api_key=PORTKEY_API_KEY,
            virtual_key=PORTKEY_VIRTUAL_KEY or None,
            provider="anthropic",
        )
        headers.update(pk_headers)
    except ImportError:
        pass  # portkey-ai not installed — use raw headers (still works)

    return Anthropic(
        api_key=PORTKEY_VIRTUAL_KEY or "dummy",   # virtual key carries the real creds
        base_url=PORTKEY_GATEWAY_URL,
        default_headers=headers,
    )


# ── Apigee token cache ──────────────────────────────────────────────
_apigee_token_cache: dict = {}  # {"token": str, "expires_at": float}


def _get_apigee_token() -> str:
    """Fetch (and cache) an OAuth2 client-credentials token from Apigee."""
    import time
    import requests as _req

    cached = _apigee_token_cache
    if cached.get("token") and time.time() < cached.get("expires_at", 0) - 30:
        return cached["token"]

    if not APIGEE_TOKEN_URL:
        raise RuntimeError("AI_GATEWAY=apigee requires APIGEE_TOKEN_URL in .env")
    if not APIGEE_CLIENT_ID or not APIGEE_CLIENT_SECRET:
        raise RuntimeError(
            "AI_GATEWAY=apigee requires APIGEE_CLIENT_ID and APIGEE_CLIENT_SECRET in .env"
        )

    resp = _req.post(
        APIGEE_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": APIGEE_CLIENT_ID,
            "client_secret": APIGEE_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()
    token = token_data["access_token"]
    expires_in = int(token_data.get("expires_in", 3600))

    _apigee_token_cache["token"] = token
    _apigee_token_cache["expires_at"] = time.time() + expires_in
    return token


def _get_apigee_client():
    """Build an Anthropic client that routes through the Apigee gateway.

    Apigee acts as a reverse proxy in front of AWS Bedrock.
    Auth: OAuth2 client-credentials bearer token (auto-refreshed on expiry).
    The gateway URL must accept Anthropic-SDK-style requests.
    """
    if not APIGEE_GATEWAY_URL:
        raise RuntimeError("AI_GATEWAY=apigee requires APIGEE_GATEWAY_URL in .env")

    token = _get_apigee_token()
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(APIGEE_EXTRA_HEADERS)

    return Anthropic(
        api_key="apigee",   # placeholder — bearer token carries real auth
        base_url=APIGEE_GATEWAY_URL,
        default_headers=headers,
    )


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
        if ex.get("team_of_teams"):
            section += f" | Team of Teams: {ex['team_of_teams']}"
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
4. Recommend the BEST-FIT WAF category AND Team of Teams with clear reasoning
5. If the user provides the current WAF tag, compare it to your recommendation and flag if it's a mismatch
6. Rate your confidence (High / Medium / Low)
7. If the story is ambiguous, explain what additional context would help

Format your response clearly with:
- **Recommended WAF Category:** [category name]
- **Team of Teams:** [team of teams value, if applicable]
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
