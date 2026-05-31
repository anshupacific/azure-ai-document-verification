"""
Document service — the pipeline orchestrator.

Top-level service the handlers call (mirrors the role of FacilitiesService in
the TS code). It composes the stage services, runs them in order, hands the
combined result to the caller-contract router, and persists:

  - a PII-free status record (status_store)  -> backs GET /documents/{id}/status
  - a PII-bearing review record (review_store) for known-ID documents that
    reach extraction -> backs the admin GET /documents/{id}/review

Flow:
    1. Stage 1 classify (image URL)
    2. If NotADocument          -> Rejected
    3. If not acceptable        -> RetakePhoto / ManualReview (tamper)
    4. If acceptable + known ID -> Document Intelligence extraction (image bytes)
         - gate fails           -> ManualReview
         - gate passes          -> optional Stage 2 -> Verified / ManualReview
    5. If acceptable + other    -> ManualReview (pending admin review)

The image is fetched once as bytes; the same bytes are reused for the
extraction call, and a URL form is used for the vision calls.
"""

import logging

from modules.documents.types.document_types import (
    DocumentType,
    KNOWN_STRUCTURED_TYPES,
    VerifyResponse,
)
from modules.documents.services.stage1_service import Stage1ClassifyService
from modules.documents.services.extraction_service import ExtractionService
from modules.documents.services.fraud_service import FraudCheckService
from modules.documents.services import status_store, review_store
from modules.documents import caller_contract
from shared import audit

logger = logging.getLogger("nijc.document_service")


class DocumentService:
    """Orchestrates the verification pipeline for one uploaded document."""

    def __init__(self):
        self._stage1 = Stage1ClassifyService()
        self._extraction = ExtractionService()
        self._fraud = FraudCheckService()

    def verify(
        self,
        document_id: str,
        image_url: str,
        image_bytes: bytes,
    ) -> VerifyResponse:
        """
        Run the pipeline and return a PII-free VerifyResponse.

        image_url  : short-lived SAS URL for the vision (GPT-4o) calls
        image_bytes: the raw bytes for the Document Intelligence call
        """
        # --- Stage 1: classify ---
        stage1 = self._stage1.classify(image_url)
        audit.log_stage("stage1", document_id, stage1)

        # NotADocument -> reject outright
        if stage1.document_type == DocumentType.NOT_A_DOCUMENT:
            return self._finish(document_id, caller_contract.route_not_a_document(document_id))

        # Not acceptable -> retake (quality) or manual review (tamper)
        if not stage1.is_acceptable:
            return self._finish(document_id, caller_contract.route_unacceptable(document_id, stage1))

        # Acceptable but not a known structured type -> pending admin review
        if stage1.document_type not in KNOWN_STRUCTURED_TYPES:
            return self._finish(document_id, caller_contract.route_pending_review(document_id, stage1))

        # --- Document Intelligence: extract + gate ---
        extraction = self._extraction.extract(image_bytes)
        audit.log_stage("extraction", document_id, extraction)

        # Persist the PII-bearing review record so admins can review this document.
        self._save_review(document_id, stage1, extraction)

        if extraction.verdict != "Proceed":
            return self._finish(
                document_id,
                caller_contract.route_extraction_failed(document_id, stage1, extraction),
            )

        # --- Stage 2: fraud check (flag-only by default) ---
        fraud = self._fraud.check(image_url)
        audit.log_stage("fraud", document_id, fraud)

        return self._finish(
            document_id,
            caller_contract.route_final(document_id, stage1, fraud),
        )

    # ----------------------------------------------------------------------

    def _finish(self, document_id: str, response: VerifyResponse) -> VerifyResponse:
        """Persist the PII-free status record, then return the response."""
        try:
            status_store.save_status_record(document_id, response.to_dict())
        except Exception:
            # Persistence failure must not change the verification outcome.
            logger.warning("failed to persist status record documentId=%s", document_id)
        return response

    def _save_review(self, document_id: str, stage1, extraction) -> None:
        """
        Persist the admin review record (extracted fields + flags). This is the
        only place extracted PII is written. Failure here is logged but does not
        block the pipeline.
        """
        record = {
            "documentId": document_id,
            "documentType": stage1.document_type.value,
            "fields": extraction.fields,
            "lowConfidenceFields": extraction.low_confidence_fields,
            "missingRequiredFields": extraction.missing_required_fields,
            "qualityFlags": {
                "blurry": stage1.quality_flags.blurry,
                "lowLight": stage1.quality_flags.low_light,
                "glareOrReflection": stage1.quality_flags.glare_or_reflection,
                "cornersCropped": stage1.quality_flags.corners_cropped,
                "screenshotOfScreen": stage1.quality_flags.screenshot_of_screen,
                "watermarkOrSample": stage1.quality_flags.watermark_or_sample,
                "expired": stage1.quality_flags.expired,
            },
            "tamperSuspicion": stage1.tamper_suspicion.value,
            "verdict": extraction.verdict,
        }
        try:
            review_store.save_review_record(document_id, record)
        except Exception:
            logger.warning("failed to persist review record documentId=%s", document_id)