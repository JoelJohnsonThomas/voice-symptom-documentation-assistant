"""
Compliance helpers for HIPAA safeguards and MedGemma terms enforcement.

Phase 3 enhancements:
- Extended PHI patterns (names, addresses, dates, insurance, device IDs)
- PHI detection scoring for audit purposes
- Redaction verification helpers
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException

from app.config import settings


MEDGEMMA_TERMS_URL = "https://ai.google.dev/gemma/terms"
MEDGEMMA_MODEL_CARD_URL = "https://huggingface.co/google/medgemma-1.5-4b-it"

# ---------------------------------------------------------------------------
# PHI Patterns — ordered by specificity (most specific first)
# Covers HIPAA Safe Harbor 18 identifiers where regex-detectable
# ---------------------------------------------------------------------------
_PHI_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # Phone numbers (US)
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
    # Email
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    # Date of birth (labelled)
    (re.compile(r"\b(?:dob|date of birth)\s*[:\-]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE), "[REDACTED_DOB]"),
    # MRN / Medical Record Number
    (re.compile(r"\bmrn\s*[:\-]?\s*[a-z0-9-]+\b", re.IGNORECASE), "[REDACTED_MRN]"),
    # Insurance / Policy numbers
    (re.compile(r"\b(?:insurance|policy|member)\s*(?:id|number|#|no\.?)\s*[:\-]?\s*[A-Z0-9-]{5,}\b", re.IGNORECASE), "[REDACTED_INSURANCE_ID]"),
    # IP addresses (v4)
    (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[REDACTED_IP]"),
    # US ZIP codes (5+4)
    (re.compile(r"\b\d{5}-\d{4}\b"), "[REDACTED_ZIP]"),
    # Dates that look like appointments/admissions (MM/DD/YYYY or YYYY-MM-DD)
    (re.compile(r"\b(?:admit|admission|discharge|appointment)\s*(?:date)?\s*[:\-]?\s*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b", re.IGNORECASE), "[REDACTED_DATE]"),
    # Device / serial numbers (labelled)
    (re.compile(r"\b(?:serial|device|imei)\s*(?:number|#|no\.?|id)?\s*[:\-]?\s*[A-Z0-9-]{6,}\b", re.IGNORECASE), "[REDACTED_DEVICE_ID]"),
    # Account numbers (labelled)
    (re.compile(r"\b(?:account|acct)\s*(?:number|#|no\.?)?\s*[:\-]?\s*[A-Z0-9-]{5,}\b", re.IGNORECASE), "[REDACTED_ACCOUNT]"),
]


def redact_phi_text(value: str) -> str:
    """Apply conservative regex-based PHI redaction to stored free text."""
    if not value:
        return value

    redacted = value
    for pattern, replacement in _PHI_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def sanitize_session_payload(session_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforce HIPAA minimum-necessary storage by redacting free-text fields
    when PHI persistence is disabled.
    """
    sanitized = dict(session_data)

    if settings.enable_phi_persistence:
        return sanitized

    sanitized["patient_name"] = None
    for field in [
        "transcript",
        "chief_complaint",
        "soap_subjective",
        "soap_objective",
        "soap_assessment",
        "soap_plan",
    ]:
        sanitized[field] = redact_phi_text(sanitized.get(field, ""))

    return sanitized


def enforce_medgemma_terms_acknowledgement() -> None:
    """
    Require explicit acknowledgement of MedGemma terms before model-backed
    endpoints are used.
    """
    if (
        settings.enforce_medgemma_terms_acknowledgement
        and not settings.medgemma_terms_acknowledged
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "MedGemma terms acknowledgement is required before model inference. "
                "Set MEDGEMMA_TERMS_ACKNOWLEDGED=true only after reviewing terms at "
                f"{MEDGEMMA_TERMS_URL} and model card at {MEDGEMMA_MODEL_CARD_URL}."
            ),
        )


def is_medgemma_terms_usable() -> bool:
    """True when MedGemma endpoints are allowed to run by policy."""
    return (
        not settings.enforce_medgemma_terms_acknowledgement
        or settings.medgemma_terms_acknowledged
    )


def build_compliance_notice() -> str:
    """Build a user-facing compliance summary for API responses."""
    hipaa_notice = (
        "HIPAA minimum-necessary mode is active (PHI persistence disabled)."
        if not settings.enable_phi_persistence
        else "PHI persistence is enabled; ensure encryption, auditing, and access controls are enforced."
    )
    terms_notice = (
        "MedGemma terms acknowledgement is enforced."
        if settings.enforce_medgemma_terms_acknowledgement
        else "MedGemma terms acknowledgement enforcement is disabled."
    )
    return (
        "Administrative documentation only; no autonomous diagnosis or triage. "
        "Clinician review is mandatory. "
        f"{hipaa_notice} {terms_notice}"
    )


def build_compliance_metadata() -> Dict[str, Any]:
    """Structured compliance metadata for UI and downstream integrations."""
    return {
        "hipaa": {
            "minimum_necessary_mode": not settings.enable_phi_persistence,
            "phi_persistence_enabled": settings.enable_phi_persistence,
            "phi_logging_enabled": settings.allow_phi_logging,
            "multi_tenancy_enabled": settings.multi_tenancy_enabled,
            "rag_audit_enabled": settings.rag_audit_enabled,
            "vector_store_encrypted": settings.rag_vector_store_encryption_enabled,
        },
        "medgemma_terms": {
            "acknowledged": settings.medgemma_terms_acknowledged,
            "enforcement_enabled": settings.enforce_medgemma_terms_acknowledgement,
            "terms_url": MEDGEMMA_TERMS_URL,
            "model_card_url": MEDGEMMA_MODEL_CARD_URL,
        },
        "review_required": True,
    }


# ---------------------------------------------------------------------------
# PHI Detection & Verification (Phase 3)
# ---------------------------------------------------------------------------

def detect_phi(text: str) -> List[Dict[str, Any]]:
    """
    Scan text for potential PHI and return detected instances.

    Returns a list of dicts with: pattern_type, match, start, end.
    Used for audit logging and verification that redaction was applied.
    """
    if not text:
        return []

    detections = []
    pattern_names = [
        "SSN", "PHONE", "EMAIL", "DOB", "MRN", "INSURANCE_ID",
        "IP", "ZIP", "DATE", "DEVICE_ID", "ACCOUNT",
    ]

    for (pattern, _replacement), name in zip(_PHI_PATTERNS, pattern_names):
        for match in pattern.finditer(text):
            detections.append({
                "pattern_type": name,
                "match": match.group()[:4] + "***",  # Truncated for safety
                "start": match.start(),
                "end": match.end(),
            })

    return detections


def verify_phi_redacted(text: str) -> Dict[str, Any]:
    """
    Verify that a text string has been properly redacted.

    Returns:
        {
            "is_clean": bool,      # True if no PHI patterns detected
            "phi_count": int,      # Number of PHI patterns found
            "pattern_types": list, # Types of PHI found
        }
    """
    detections = detect_phi(text)
    pattern_types = list({d["pattern_type"] for d in detections})
    return {
        "is_clean": len(detections) == 0,
        "phi_count": len(detections),
        "pattern_types": pattern_types,
    }


def redact_for_vector_store(text: str) -> Tuple[str, Dict[str, Any]]:
    """
    Redact PHI from text destined for the vector store, returning
    both the redacted text and a verification report.

    Uses Presidio NER-based detection (if available) for comprehensive
    coverage including patient names and addresses, with regex fallback.
    """
    try:
        from app.security.phi_detector import get_phi_detector
        detector = get_phi_detector()
        redacted, scan_result = detector.redact_for_storage(text)
        verification = {
            "is_clean": scan_result.is_clean,
            "phi_count": scan_result.detection_count,
            "pattern_types": scan_result.entity_types_found,
            "method": scan_result.method,
        }
        return redacted, verification
    except Exception:
        # Fallback to regex-only if Presidio import fails
        redacted = redact_phi_text(text)
        verification = verify_phi_redacted(redacted)
        if not verification["is_clean"]:
            redacted = redact_phi_text(redacted)
            verification = verify_phi_redacted(redacted)
        return redacted, verification
