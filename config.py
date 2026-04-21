"""
WAF Classifier — Configuration & environment setup.
Extracted from app.py to keep the monolith manageable.
"""

# Fix macOS fork crash with Python threading on Apple Silicon
import os
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

import logging

# ── .env Loading ──────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ[_k.strip()] = _v.strip()

# ── AI Backend Detection ───────────────────────────────────────────
try:
    from anthropic import AnthropicBedrock as _AnthropicBedrock
    _BEDROCK_AVAILABLE = True
except ImportError:
    _BEDROCK_AVAILABLE = False


# Priority: ANTHROPIC_API_KEY in .env → AWS Bedrock (uses AWS env creds)
def _setup_ai_backend():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return "anthropic", "claude-sonnet-4-5-20250929"
    # No API key — try Bedrock
    bedrock_model = os.environ.get(
        "BEDROCK_MODEL_ID",
        "anthropic.claude-sonnet-4-5-20250929-v1:0"
    )
    return "bedrock", bedrock_model


AI_BACKEND, AI_MODEL = _setup_ai_backend()

# ── Paths ─────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "waf_history.db")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
BASELINE_DIR = os.path.join(os.path.dirname(__file__), "baselines")
os.makedirs(BASELINE_DIR, exist_ok=True)

# ── Application Root (URL prefix for reverse-proxy deployments) ───────
# Set APPLICATION_ROOT=/h591-wafui in .env to serve the app under a sub-path.
# Leave unset (or empty) for root-path deployment (default, local dev).
APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "").rstrip("/")

# ── Rate Limiting ─────────────────────────────────────────────────────
MAX_BULK_JOBS_PER_MINUTE = 5  # Default; overridden by settings

# ── Logging ───────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
