"""
Audit logging.

Writes structured, metadata-only audit records for each pipeline stage. This is
the compliance layer required for attorney-client-privileged documents:

  - NEVER logs prompts, responses, image bytes, or extracted field VALUES.
  - Logs only metadata: stage, documentId, document type, verdict/acceptability,
    confidence numbers, and field NAMES (not values).
  - reasons[] / tamperSignals[] are scrubbed for digit runs (>= 5 digits) before
    logging, as a backstop against any number (SSN, doc number) leaking in.

Uses the standard logging module, which Azure Functions captures into
Application Insights. Field values never reach this layer by design — the
extraction result carries them, but we only read names and confidences here.
"""

import re
import logging

logger = logging.getLogger("nijc.audit")

# Matches a run of 5 or more digits (doc numbers, SSNs, A-numbers, etc.)
_DIGIT_RUN = re.compile(r"\d{5,}")


def scrub(text: str) -> str:
    """Replace any run of 5+ digits with a redaction marker."""
    if not isinstance(text, str):
        return text
    return _DIGIT_RUN.sub("[redacted]", text)


def scrub_list(items: list[str]) -> list[str]:
    return [scrub(item) for item in (items or [])]


def log_stage(stage: str, document_id: str, result) -> None:
    """
    Log one pipeline stage as metadata only. Dispatches on the stage name so we
    only ever read safe attributes off the typed result objects.
    """
    try:
        if stage == "stage1":
            _log_stage1(document_id, result)
        elif stage == "extraction":
            _log_extraction(document_id, result)
        elif stage == "fraud":
            _log_fraud(document_id, result)
        else:
            logger.info("audit stage=%s documentId=%s", stage, document_id)
    except Exception:
        # Logging must never break the pipeline.
        logger.warning("audit logging failed stage=%s documentId=%s", stage, document_id)


def _log_stage1(document_id: str, r) -> None:
    logger.info(
        "audit stage=stage1 documentId=%s type=%s typeConf=%.3f acceptable=%s "
        "acceptConf=%.3f tamper=%s reasons=%s",
        document_id,
        r.document_type.value,
        r.document_type_confidence,
        r.is_acceptable,
        r.acceptable_confidence,
        r.tamper_suspicion.value,
        scrub_list(r.reasons),
    )


def _log_extraction(document_id: str, r) -> None:
    # Field NAMES + confidences only — never values.
    field_names = sorted(r.fields.keys()) if r.fields else []
    logger.info(
        "audit stage=extraction documentId=%s verdict=%s docType=%s "
        "fields=%s lowConf=%s missing=%s reason=%s",
        document_id,
        r.verdict,
        r.doc_type,
        field_names,
        r.low_confidence_fields,
        r.missing_required_fields,
        r.reason,
    )


def _log_fraud(document_id: str, r) -> None:
    logger.info(
        "audit stage=fraud documentId=%s verdict=%s score=%s signals=%s",
        document_id,
        r.verdict,
        r.legitimacy_score,
        scrub_list(r.tamper_signals),
    )