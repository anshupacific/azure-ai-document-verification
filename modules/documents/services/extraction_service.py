"""
Document Intelligence extraction service.

Refactored from the POC doc_intelligence_extract.py into a service class.
Runs prebuilt-idDocument against an image, extracts structured fields with
per-field confidence, and applies the confidence gate.

Gate thresholds and the required-fields list come from config (Function App
settings), so they are tunable without a code change.
"""

from azure.core.exceptions import HttpResponseError

from shared import config
from shared.clients import build_doc_intelligence_client
from modules.documents.types.document_types import ExtractionResult


class ExtractionService:
    """Extracts ID-document fields and applies the confidence gate."""

    def __init__(self):
        self._client = build_doc_intelligence_client()
        self._model_id = config.DOC_INTELLIGENCE_ID_MODEL
        self._threshold = config.EXTRACTION_FIELD_CONFIDENCE_THRESHOLD
        self._required_fields = config.EXTRACTION_REQUIRED_FIELDS

    def extract(self, image_bytes: bytes) -> ExtractionResult:
        """
        Run prebuilt-idDocument against the raw image bytes and return an
        ExtractionResult with a gate verdict. On API failure -> ManualReview.
        """
        try:
            poller = self._client.begin_analyze_document(
                self._model_id,
                body=image_bytes,
                content_type="application/octet-stream",
            )
            result = poller.result()

            if not result.documents:
                return ExtractionResult(
                    verdict="ManualReview",
                    reason="no_id_document_detected",
                )

            doc = result.documents[0]
            fields = self._collect_fields(doc)
            return self._apply_gate(fields, doc_type=getattr(doc, "doc_type", None))

        except HttpResponseError as e:
            return ExtractionResult(
                verdict="ManualReview",
                reason="ai_unavailable",
            )

    @staticmethod
    def _collect_fields(doc) -> dict:
        """Map the SDK document fields into {name: {value, confidence}}."""
        out = {}
        for name, fld in (doc.fields or {}).items():
            out[name] = {
                "value": getattr(fld, "content", None),
                "confidence": getattr(fld, "confidence", None),
            }
        return out

    def _apply_gate(self, fields: dict, doc_type=None) -> ExtractionResult:
        """
        Proceed only if every configured required field is present and at or
        above the confidence threshold. Otherwise route to ManualReview.
        """
        low_confidence = []
        missing = []

        for required in self._required_fields:
            if required not in fields:
                missing.append(required)
                continue
            conf = fields[required]["confidence"]
            if conf is None or conf < self._threshold:
                low_confidence.append({"field": required, "confidence": conf})

        if low_confidence or missing:
            reason = "low_confidence" if low_confidence else "missing_required_fields"
            return ExtractionResult(
                verdict="ManualReview",
                doc_type=doc_type,
                fields=fields,
                low_confidence_fields=low_confidence,
                missing_required_fields=missing,
                reason=reason,
            )

        return ExtractionResult(
            verdict="Proceed",
            doc_type=doc_type,
            fields=fields,
        )