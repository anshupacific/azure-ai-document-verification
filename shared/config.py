"""
Central configuration for the NIJC document API.

Every tunable value — credentials, thresholds, timeouts, the prompt version —
is read from environment variables (Function App application settings in Azure,
local.settings.json locally). Defaults are sensible but every value can be
adjusted from the Function App without a code change.
"""

import os


def _get_float(key: str, default: float) -> float:
    """Read a float setting, falling back to default if unset or invalid."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_list(key: str, default: list[str]) -> list[str]:
    """Comma-separated env value -> list of trimmed strings."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Azure AI Foundry (GPT-4o) credentials
# ---------------------------------------------------------------------------
AZURE_AI_FOUNDRY_ENDPOINT = _get_str("AZURE_AI_FOUNDRY_ENDPOINT")
AZURE_AI_FOUNDRY_KEY = _get_str("AZURE_AI_FOUNDRY_KEY")
AZURE_GPT4O_DEPLOYMENT = _get_str("AZURE_GPT4O_DEPLOYMENT", "gpt-4o")
AZURE_OPENAI_API_VERSION = _get_str("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")

# ---------------------------------------------------------------------------
# Azure AI Document Intelligence credentials
# ---------------------------------------------------------------------------
AZURE_DOC_INTELLIGENCE_ENDPOINT = _get_str("AZURE_DOC_INTELLIGENCE_ENDPOINT")
AZURE_DOC_INTELLIGENCE_KEY = _get_str("AZURE_DOC_INTELLIGENCE_KEY")
DOC_INTELLIGENCE_ID_MODEL = _get_str("DOC_INTELLIGENCE_ID_MODEL", "prebuilt-idDocument")
DOC_INTELLIGENCE_LAYOUT_MODEL = _get_str("DOC_INTELLIGENCE_LAYOUT_MODEL", "prebuilt-layout")

# ---------------------------------------------------------------------------
# Thresholds — all tunable from Function App settings
# ---------------------------------------------------------------------------
# Stage 1: minimum classification confidence to treat a type as reliable.
STAGE1_DOC_TYPE_CONFIDENCE_THRESHOLD = _get_float(
    "STAGE1_DOC_TYPE_CONFIDENCE_THRESHOLD", 0.70
)

# Document Intelligence: per-field confidence gate. A required field below this
# routes the document to manual review.
EXTRACTION_FIELD_CONFIDENCE_THRESHOLD = _get_float(
    "EXTRACTION_FIELD_CONFIDENCE_THRESHOLD", 0.90
)

# Which extracted fields are treated as "required" for the gate. Gating on a
# short critical set avoids over-routing legitimate documents to review.
EXTRACTION_REQUIRED_FIELDS = _get_list(
    "EXTRACTION_REQUIRED_FIELDS",
    ["DocumentNumber", "DateOfBirth", "LastName"],
)

# Stage 2: legitimacy score at or above which a document may be auto-verified.
STAGE2_LEGITIMACY_THRESHOLD = _get_float("STAGE2_LEGITIMACY_THRESHOLD", 0.85)

# Whether Stage 2 may auto-verify at all. POC found GPT-4o fraud scoring
# unreliable, so the safe default is flag-only (never auto-verify).
STAGE2_ALLOW_AUTO_VERIFY = _get_str("STAGE2_ALLOW_AUTO_VERIFY", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Timeouts and operational settings
# ---------------------------------------------------------------------------
# Per-call AI timeout (seconds). Production p95 budget is 4s; configurable so
# slower environments or batch eval runs can raise it.
AI_TIMEOUT_SECONDS = _get_float("AI_TIMEOUT_SECONDS", 4.0)

# SAS URL lifetime for the uploaded blob (minutes).
SAS_URL_TTL_MINUTES = _get_int("SAS_URL_TTL_MINUTES", 5)

# Prompt version for A/B and rollback without redeploy.
PROMPT_VERSION = _get_str("PROMPT_VERSION", "v1")

# Deterministic generation settings for the GPT-4o calls.
AI_TEMPERATURE = _get_float("AI_TEMPERATURE", 0.0)
AI_TOP_P = _get_float("AI_TOP_P", 0.1)