"""
Document module types.

Mirrors the TypeScript facilities.types.ts pattern: request shapes, response
shapes, status enums, and valid-value constants in one place. Uses dataclasses
and string enums (Python's equivalent of TS interfaces + union types).
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums (= TS string-union types)
# ---------------------------------------------------------------------------
class DocumentType(str, Enum):
    PASSPORT = "Passport"
    SSN_CARD = "SSNCard"
    DRIVERS_LICENCE = "DriversLicence"
    BIRTH_CERTIFICATE = "BirthCertificate"
    MARRIAGE_CERTIFICATE = "MarriageCertificate"
    GREEN_CARD = "GreenCard"
    EAD = "EAD"
    I94 = "I94"
    I589 = "I589"
    I765 = "I765"
    OTHER_USCIS = "OtherUSCIS"
    OTHER_DOCUMENT = "OtherDocument"
    NOT_A_DOCUMENT = "NotADocument"


class VerificationStatus(str, Enum):
    """The client-facing status returned by the verify endpoint."""
    VERIFIED = "Verified"
    MANUAL_REVIEW = "ManualReview"
    REJECTED = "Rejected"
    RETAKE_PHOTO = "RetakePhoto"


class TamperSuspicion(str, Enum):
    NONE = "None"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# Document types that have a known structured extraction path (auto-trigger
# Document Intelligence). Other acceptable types go to pending admin review.
KNOWN_STRUCTURED_TYPES = {
    DocumentType.PASSPORT,
    DocumentType.SSN_CARD,
    DocumentType.DRIVERS_LICENCE,
    DocumentType.GREEN_CARD,
    DocumentType.EAD,
}


# ---------------------------------------------------------------------------
# Request shapes (= TS request interfaces)
# ---------------------------------------------------------------------------
@dataclass
class VerifyRequest:
    """
    Body of POST /documents/verify. The raw image is NOT sent here — only a
    reference to the already-uploaded blob plus case context.
    """
    document_id: str
    case_id: str
    document_slot: str          # e.g. "passport"
    blob_reference: str


# ---------------------------------------------------------------------------
# Internal pipeline result (passed between services; NOT sent to the client)
# ---------------------------------------------------------------------------
@dataclass
class QualityFlags:
    blurry: bool = False
    low_light: bool = False
    glare_or_reflection: bool = False
    corners_cropped: bool = False
    screenshot_of_screen: bool = False
    watermark_or_sample: bool = False
    expired: bool | None = None


@dataclass
class Stage1Result:
    """Output of the Stage 1 classification service."""
    document_type: DocumentType
    document_type_confidence: float
    is_acceptable: bool
    acceptable_confidence: float
    quality_flags: QualityFlags
    tamper_suspicion: TamperSuspicion
    reasons: list[str] = field(default_factory=list)
    language: str | None = None


@dataclass
class ExtractionResult:
    """Output of the Document Intelligence extraction service."""
    verdict: str                          # "Proceed" | "ManualReview"
    doc_type: str | None = None
    fields: dict = field(default_factory=dict)        # name -> {value, confidence}
    low_confidence_fields: list[dict] = field(default_factory=list)
    missing_required_fields: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass
class FraudResult:
    """Output of the Stage 2 fraud-check service."""
    verdict: str                          # "Verified" | "ManualReview"
    legitimacy_score: float | None = None
    tamper_signals: list[str] = field(default_factory=list)
    reason: str | None = None


# ---------------------------------------------------------------------------
# Client-facing response (= TS response interface) — PII-FREE
# ---------------------------------------------------------------------------
@dataclass
class VerifyResponse:
    """
    What the verify/status endpoints return to the portal. Carries NO PII:
    no extracted field values, no model reasons[] — only status + a message key.
    """
    document_id: str
    status: VerificationStatus
    document_type: DocumentType | None
    message_key: str
    requires_retake: bool = False

    def to_dict(self) -> dict:
        return {
            "documentId": self.document_id,
            "status": self.status.value,
            "documentType": self.document_type.value if self.document_type else None,
            "messageKey": self.message_key,
            "requiresRetake": self.requires_retake,
        }