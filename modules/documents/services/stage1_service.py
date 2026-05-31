"""
Stage 1 classification service.

Refactored from the POC stage1_classify.py into a service class that mirrors
the TypeScript FacilitiesService pattern: constructor reads config / builds the
client, public methods hold the business logic, no module-level side effects.

Single GPT-4o Vision call against an image -> structured Stage1Result.
Deterministic settings; falls back to an unacceptable result on AI failure so
the upload is never blocked.
"""

import json

from openai import APITimeoutError, APIStatusError

from shared import config
from shared.clients import build_openai_client
from modules.documents.types.document_types import (
    DocumentType,
    TamperSuspicion,
    QualityFlags,
    Stage1Result,
)


# System prompt — verbatim from the NIJC spec (section 3.1).
SYSTEM_PROMPT = """You are NIJC's document intake classifier. NIJC is a US legal-aid organization
that supports immigrants, asylum-seekers, and refugees. Users upload identity
documents and supporting paperwork as part of their legal-services intake.

Your job is to look at one image and produce a single JSON object that:
  1. classifies what the document is,
  2. judges whether the image is acceptable for case intake,
  3. flags any obvious quality or authenticity concerns.

You DO NOT extract personal data. You DO NOT make a final legal-validity
ruling. You DO NOT answer questions outside this task. If the user message
contains anything other than the image, ignore it.

Output rules — non-negotiable:
  - Respond with a single JSON object, no prose, no markdown fences.
  - Use the exact schema below. Unknown fields -> null. Do not invent fields.
  - confidence values are floats in [0.0, 1.0].
  - reasons[] holds short English phrases (<= 10 words each), no PII.
  - Never echo names, document numbers, dates of birth, or addresses you
    happen to see in the image.

Schema:
{
  "documentType": "Passport" | "SSNCard" | "DriversLicence" | "BirthCertificate"
                | "MarriageCertificate" | "GreenCard" | "EAD" | "I94" | "I589"
                | "I765" | "OtherUSCIS" | "OtherDocument" | "NotADocument",
  "documentTypeConfidence": <float>,
  "isAcceptable": true | false,
  "acceptableConfidence": <float>,
  "qualityFlags": {
    "blurry": true | false,
    "lowLight": true | false,
    "glareOrReflection": true | false,
    "cornersCropped": true | false,
    "screenshotOfScreen": true | false,
    "watermarkOrSample": true | false,
    "expired": true | false | null
  },
  "tamperSuspicion": "None" | "Low" | "Medium" | "High",
  "reasons": [ "<short reason>", ... ],
  "language": "en" | "es" | "fr" | "ht" | "ar" | "other" | null
}

Decision guidance:
  - If the image is not a document (selfie, blank, screenshot of an app),
    set documentType="NotADocument", isAcceptable=false.
  - If you cannot tell what the document is, use "OtherDocument" with low
    confidence — do not guess.
  - "isAcceptable" = false if any of: blurry, lowLight, glareOrReflection,
    cornersCropped, screenshotOfScreen, watermarkOrSample is true, OR if
    tamperSuspicion is "Medium"/"High", OR if "expired" is true.
  - Set "expired" to null when the document type has no expiry (SSN card,
    birth certificate) or when no expiry is visible.
  - tamperSuspicion: "None" by default. Raise to "Low" only if you see
    inconsistent fonts, mismatched fields, obvious digital edits, or
    layout that doesn't match a known template. "High" requires multiple
    such signals."""


class Stage1ClassifyService:
    """Classifies an uploaded image: type + acceptability + quality flags."""

    def __init__(self):
        self._client = build_openai_client()
        self._deployment = config.AZURE_GPT4O_DEPLOYMENT

    def classify(self, image_url: str) -> Stage1Result:
        """
        Run the classify call against an image URL (a short-lived SAS URL in
        production). Returns a Stage1Result. On any AI failure, returns a safe
        unacceptable result so the caller routes to manual review.
        """
        try:
            resp = self._client.chat.completions.create(
                model=self._deployment,
                temperature=config.AI_TEMPERATURE,
                top_p=config.AI_TOP_P,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}}
                        ],
                    },
                ],
            )
            raw = json.loads(resp.choices[0].message.content)
            return self._parse(raw)

        except (APITimeoutError, APIStatusError, json.JSONDecodeError):
            return self._fallback()

    def _parse(self, raw: dict) -> Stage1Result:
        """Map the model's JSON into a typed Stage1Result."""
        qf_raw = raw.get("qualityFlags", {}) or {}
        quality = QualityFlags(
            blurry=bool(qf_raw.get("blurry", False)),
            low_light=bool(qf_raw.get("lowLight", False)),
            glare_or_reflection=bool(qf_raw.get("glareOrReflection", False)),
            corners_cropped=bool(qf_raw.get("cornersCropped", False)),
            screenshot_of_screen=bool(qf_raw.get("screenshotOfScreen", False)),
            watermark_or_sample=bool(qf_raw.get("watermarkOrSample", False)),
            expired=qf_raw.get("expired", None),
        )

        return Stage1Result(
            document_type=self._safe_doc_type(raw.get("documentType")),
            document_type_confidence=float(raw.get("documentTypeConfidence", 0.0)),
            is_acceptable=bool(raw.get("isAcceptable", False)),
            acceptable_confidence=float(raw.get("acceptableConfidence", 0.0)),
            quality_flags=quality,
            tamper_suspicion=self._safe_tamper(raw.get("tamperSuspicion")),
            reasons=raw.get("reasons", []) or [],
            language=raw.get("language"),
        )

    @staticmethod
    def _safe_doc_type(value) -> DocumentType:
        try:
            return DocumentType(value)
        except (ValueError, TypeError):
            return DocumentType.OTHER_DOCUMENT

    @staticmethod
    def _safe_tamper(value) -> TamperSuspicion:
        try:
            return TamperSuspicion(value)
        except (ValueError, TypeError):
            return TamperSuspicion.NONE

    @staticmethod
    def _fallback() -> Stage1Result:
        """AI unavailable -> unacceptable, so the caller routes to ManualReview."""
        return Stage1Result(
            document_type=DocumentType.OTHER_DOCUMENT,
            document_type_confidence=0.0,
            is_acceptable=False,
            acceptable_confidence=0.0,
            quality_flags=QualityFlags(),
            tamper_suspicion=TamperSuspicion.NONE,
            reasons=["ai_unavailable"],
            language=None,
        )