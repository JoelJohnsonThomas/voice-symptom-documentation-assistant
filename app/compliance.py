"""Compliance helpers for HIPAA safeguards and MedGemma terms enforcement."""

from __future__ import annotations

import re
from typing import Any, Dict

from fastapi import HTTPException

from app.config import settings


MEDGEMMA_TERMS_URL = "https://ai.google.dev/gemma/terms"
MEDGEMMA_MODEL_CARD_URL = "https://huggingface.co/google/medgemma-1.5-4b-it"

_PHI_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[REDACTED_PHONE]"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:dob|date of birth)\s*[:\-]?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE), "[REDACTED_DOB]"),
    (re.compile(r"\bmrn\s*[:\-]?\s*[a-z0-9-]+\b", re.IGNORECASE), "[REDACTED_MRN]"),
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
        },
        "medgemma_terms": {
            "acknowledged": settings.medgemma_terms_acknowledged,
            "enforcement_enabled": settings.enforce_medgemma_terms_acknowledgement,
            "terms_url": MEDGEMMA_TERMS_URL,
            "model_card_url": MEDGEMMA_MODEL_CARD_URL,
        },
        "review_required": True,
    }
