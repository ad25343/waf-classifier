"""
WAF Classifier — Global mutable state.
Extracted from app.py so every module can import shared state without
circular dependencies.
"""

# In-memory store for WAF definitions
waf_store = {
    "definitions": None,
    "raw_text": "",
    "filename": "",
    "categories": []
}

# ── Fuzzy WAF Category Matching ────────────────────────────────────────
DEFAULT_WAF_CATEGORIES = [
    "KTLO (Keep the Lights On)",
    "Business Maintenance",
    "Technical Maintenance",
    "Regulatory (Operational)",
    "Regulatory Mandated Change",
    "Enterprise Strategic Priority",
    "Top Divisional Priority",
    "Other Blocked Priority",
]

WAF_ALIASES = {
    "ktlo": "KTLO (Keep the Lights On)",
    "keep the lights on": "KTLO (Keep the Lights On)",
    "keep lights on": "KTLO (Keep the Lights On)",
    "biz maintenance": "Business Maintenance",
    "bus maintenance": "Business Maintenance",
    "business maint": "Business Maintenance",
    "tech maintenance": "Technical Maintenance",
    "technical maint": "Technical Maintenance",
    "tech debt": "Technical Maintenance",
    "reg operational": "Regulatory (Operational)",
    "regulatory operational": "Regulatory (Operational)",
    "reg ops": "Regulatory (Operational)",
    "reg mandated": "Regulatory Mandated Change",
    "regulatory mandated": "Regulatory Mandated Change",
    "reg change": "Regulatory Mandated Change",
    "enterprise strategic": "Enterprise Strategic Priority",
    "esp": "Enterprise Strategic Priority",
    "strategic priority": "Enterprise Strategic Priority",
    "top divisional": "Top Divisional Priority",
    "tdp": "Top Divisional Priority",
    "divisional priority": "Top Divisional Priority",
    "other blocked": "Other Blocked Priority",
    "obp": "Other Blocked Priority",
    "blocked priority": "Other Blocked Priority",
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

# ── Background Job Tracking ───────────────────────────────────────────
# Stores in-progress and completed bulk-verify jobs for async processing
verify_jobs = {}  # job_id -> { status, progress, total_batches, completed_batches, results, error, ... }

# ── Preview Store ─────────────────────────────────────────────────────
_preview_store: dict = {}  # preview_id -> { "df": DataFrame, "filename": str, "ext": str, "created": float }
_PREVIEW_TTL = 600  # 10 minutes

# ── Rate Limiting ─────────────────────────────────────────────────────
_rate_limit_store: dict = {}  # ip -> [timestamps]
