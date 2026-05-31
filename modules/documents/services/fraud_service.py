"""
Stage 2 fraud / tamper-check service.

Refactored from the POC stage2_fraud_check.py into a service class.
A single GPT-4o Vision call returns a legitimacy score and tamper signals.

IMPORTANT: POC testing found GPT-4o fraud scoring unreliable. By default this
service is FLAG-ONLY — it never auto-verifies; a clean score still routes to
ManualReview. Auto-verify is only possible if STAGE2_ALLOW_AUTO_VERIFY is set
true in the Function App settings, and even then only above the configured
legitimacy threshold with no suspicion flags.

The prompt is NOT in the NIJC spec (marked "future"); it is designed here from
the tamper signals the spec describes. Treat it as a first draft to be tuned.
"""

import json

from openai import APITimeoutError, APIStatusError

from shared import config
from shared.clients import build_openai_client
from modules.documents.types.document_types import FraudResult


SYSTEM_PROMPT = """You are NIJC's document authenticity reviewer. NIJC is a US legal-aid
organization serving immigrants, asylum-seekers, and refugees. An identity
document image has already passed an intake quality check. Your task now is a
deeper authenticity / tamper review of that single image.

You are NOT making a legal-validity ruling. You do NOT decide whether the
person is who they say they are. You only assess whether the IMAGE shows
signs of digital manipulation, forgery, or capture artifacts that warrant
human review.

You DO NOT extract or repeat personal data. Never echo names, document
numbers, dates of birth, or addresses you see in the image.

Examine the image for these tamper / authenticity signals:
  - Inconsistent fonts, kerning, or alignment within fields
  - Fields that look pasted, recolored, or digitally edited
  - Mismatched or misaligned background security patterns
  - Layout that does not match a known template for that document type
  - Photo substitution signs (edge halos, mismatched lighting on the portrait)
  - Moire / pixel-grid patterns indicating a photo of a screen
  - Cloning / smudging artifacts, repeated texture, or compression seams
  - Mismatched data (e.g. MRZ that disagrees with the printed fields)

Output rules — non-negotiable:
  - Respond with a single JSON object. No prose, no markdown fences.
  - Use the exact schema below. Do not invent fields.
  - legitimacyScore is a float in [0.0, 1.0]: 1.0 = looks fully authentic,
    0.0 = clear forgery. Be conservative: when genuinely unsure, score lower.
  - tamperSignals[] holds short English phrases (<= 10 words each), no PII.

Schema:
{
  "legitimacyScore": <float>,
  "tamperSignals": [ "<short signal>", ... ],
  "screenCaptureSuspected": true | false,
  "photoSubstitutionSuspected": true | false,
  "templateMismatch": true | false
}"""


class FraudCheckService:
    """Stage 2 tamper review. Flag-only by default."""

    def __init__(self):
        self._client = build_openai_client()
        self._deployment = config.AZURE_GPT4O_DEPLOYMENT
        self._threshold = config.STAGE2_LEGITIMACY_THRESHOLD
        self._allow_auto_verify = config.STAGE2_ALLOW_AUTO_VERIFY

    def check(self, image_url: str) -> FraudResult:
        """
        Run the tamper check against an image URL. Returns a FraudResult whose
        verdict is enforced in code, not taken from the model. On AI failure ->
        ManualReview (never auto-verify on error).
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
            return self._apply_verdict(raw)

        except (APITimeoutError, APIStatusError, json.JSONDecodeError):
            return FraudResult(verdict="ManualReview", reason="ai_unavailable")

    def _apply_verdict(self, raw: dict) -> FraudResult:
        """
        Decide the verdict in code. Auto-verify only if explicitly enabled AND
        the score clears the threshold AND no suspicion flag is set. Otherwise
        ManualReview.
        """
        score = raw.get("legitimacyScore")
        signals = raw.get("tamperSignals", []) or []
        flagged = (
            bool(raw.get("screenCaptureSuspected"))
            or bool(raw.get("photoSubstitutionSuspected"))
            or bool(raw.get("templateMismatch"))
        )

        can_verify = (
            self._allow_auto_verify
            and isinstance(score, (int, float))
            and score >= self._threshold
            and not flagged
        )

        return FraudResult(
            verdict="Verified" if can_verify else "ManualReview",
            legitimacy_score=score if isinstance(score, (int, float)) else None,
            tamper_signals=signals,
        )