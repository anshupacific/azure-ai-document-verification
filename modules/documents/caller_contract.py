"""
Caller contract — routing logic.

Turns each pipeline outcome into a PII-free VerifyResponse: a status, a message
key (the portal resolves the user-facing text from its i18n table), and a
retake flag. The model's reasons[] and any extracted values never appear here —
user-facing strings are keyed off quality flags only.

This is the Python equivalent of the design doc's caller-contract table, kept
in its own module so the routing decisions are unit-testable without running
the AI pipeline.
"""

from modules.documents.types.document_types import (
    DocumentType,
    TamperSuspicion,
    VerificationStatus,
    VerifyResponse,
    Stage1Result,
    ExtractionResult,
    FraudResult,
)


# Message keys the portal maps to localized strings.
MSG_NOT_A_DOCUMENT = "verify.not_a_document"
MSG_RETAKE_BLURRY = "verify.retake.blurry"
MSG_RETAKE_LOW_LIGHT = "verify.retake.low_light"
MSG_RETAKE_GLARE = "verify.retake.glare"
MSG_RETAKE_CROPPED = "verify.retake.corners_cropped"
MSG_RETAKE_SCREENSHOT = "verify.retake.screenshot"
MSG_RETAKE_EXPIRED = "verify.retake.expired"
MSG_RETAKE_GENERIC = "verify.retake.generic"
MSG_MANUAL_REVIEW = "verify.manual_review"
MSG_PENDING_REVIEW = "verify.pending_review"
MSG_VERIFIED = "verify.success"


def route_not_a_document(document_id: str) -> VerifyResponse:
    """Image isn't a document -> reject, ask for re-upload."""
    return VerifyResponse(
        document_id=document_id,
        status=VerificationStatus.REJECTED,
        document_type=DocumentType.NOT_A_DOCUMENT,
        message_key=MSG_NOT_A_DOCUMENT,
        requires_retake=True,
    )


def route_unacceptable(document_id: str, stage1: Stage1Result) -> VerifyResponse:
    """
    Acceptable == false. If tamper is suspected -> ManualReview (admin notified,
    generic message). Otherwise it's a quality problem -> RetakePhoto with a
    specific message key derived from the quality flags.
    """
    if stage1.tamper_suspicion in (TamperSuspicion.MEDIUM, TamperSuspicion.HIGH):
        return VerifyResponse(
            document_id=document_id,
            status=VerificationStatus.MANUAL_REVIEW,
            document_type=stage1.document_type,
            message_key=MSG_MANUAL_REVIEW,
            requires_retake=False,
        )

    return VerifyResponse(
        document_id=document_id,
        status=VerificationStatus.RETAKE_PHOTO,
        document_type=stage1.document_type,
        message_key=_retake_message_key(stage1),
        requires_retake=True,
    )


def route_pending_review(document_id: str, stage1: Stage1Result) -> VerifyResponse:
    """Acceptable, but not a known structured ID type -> pending admin review."""
    return VerifyResponse(
        document_id=document_id,
        status=VerificationStatus.MANUAL_REVIEW,
        document_type=stage1.document_type,
        message_key=MSG_PENDING_REVIEW,
        requires_retake=False,
    )


def route_extraction_failed(
    document_id: str, stage1: Stage1Result, extraction: ExtractionResult
) -> VerifyResponse:
    """Extraction gate failed (low confidence / missing fields) -> ManualReview."""
    return VerifyResponse(
        document_id=document_id,
        status=VerificationStatus.MANUAL_REVIEW,
        document_type=stage1.document_type,
        message_key=MSG_MANUAL_REVIEW,
        requires_retake=False,
    )


def route_final(
    document_id: str, stage1: Stage1Result, fraud: FraudResult
) -> VerifyResponse:
    """Final stage: Stage 2 verdict decides Verified vs ManualReview."""
    if fraud.verdict == "Verified":
        return VerifyResponse(
            document_id=document_id,
            status=VerificationStatus.VERIFIED,
            document_type=stage1.document_type,
            message_key=MSG_VERIFIED,
            requires_retake=False,
        )

    return VerifyResponse(
        document_id=document_id,
        status=VerificationStatus.MANUAL_REVIEW,
        document_type=stage1.document_type,
        message_key=MSG_MANUAL_REVIEW,
        requires_retake=False,
    )


def _retake_message_key(stage1: Stage1Result) -> str:
    """
    Pick a specific retake message from the quality flags, in priority order.
    Keyed off flags only — never off the model's free-text reasons[].
    """
    qf = stage1.quality_flags
    if qf.screenshot_of_screen:
        return MSG_RETAKE_SCREENSHOT
    if qf.blurry:
        return MSG_RETAKE_BLURRY
    if qf.corners_cropped:
        return MSG_RETAKE_CROPPED
    if qf.glare_or_reflection:
        return MSG_RETAKE_GLARE
    if qf.low_light:
        return MSG_RETAKE_LOW_LIGHT
    if qf.expired is True:
        return MSG_RETAKE_EXPIRED
    return MSG_RETAKE_GENERIC