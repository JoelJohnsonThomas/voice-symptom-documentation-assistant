"""
Safety Guardrails for the AI Voice Assistant.

Phase 1:
- Emergency detection (chest pain, breathing difficulty, suicidal ideation)
- Non-diagnostic language enforcement
- Red flag symptom alerts for clinician review

Phase 2:
- PHI redaction for conversation persistence (via compliance.redact_phi_text)
- Conversation encryption at rest (via app.encryption)
- Audit logging for emergency escalations and conversation events
- Treatment/dosage recommendation filtering
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


# Emergency phrases that require immediate 911 advisory
EMERGENCY_PATTERNS = [
    r"can'?t\s+breathe",
    r"difficulty\s+breathing",
    r"trouble\s+breathing",
    r"shortness\s+of\s+breath.*severe",
    r"chest\s+pain.*radiat",
    r"crushing\s+chest",
    r"losing\s+consciousness",
    r"passed?\s+out",
    r"suicid",
    r"kill\s+(myself|me)",
    r"want\s+to\s+die",
    r"self[- ]?harm",
    r"overdos",
    r"severe\s+bleeding",
    r"uncontrollable\s+bleeding",
    r"seizure.*now",
    r"having\s+a\s+stroke",
    r"face\s+drooping",
    r"slurred\s+speech.*sudden",
    r"sudden.*worst\s+headache",
    r"anaphyla",
    r"allergic\s+reaction.*severe",
    r"throat.*swelling.*can'?t",
]

# Compiled patterns for performance
_EMERGENCY_RE = [re.compile(p, re.IGNORECASE) for p in EMERGENCY_PATTERNS]

# Diagnostic language patterns the assistant must NOT use
DIAGNOSTIC_PATTERNS = [
    (r"\byou\s+(have|got|may\s+have|might\s+have|could\s+have)\b", "your doctor will evaluate"),
    (r"\bdiagnos[ei]s?\b", "clinical assessment"),
    (r"\bthis\s+(sounds?\s+like|looks?\s+like|appears?\s+to\s+be)\b", "this information will help your clinician"),
    (r"\byou\s+should\s+take\b", "your doctor may recommend"),
    (r"\bi\s+think\s+(you|it)\b", "your clinician will determine"),
    (r"\bprescri(be|ption)\b", "your doctor can discuss treatment options"),
    (r"\bmy\s+(diagnosis|assessment)\s+is\b", "the documented findings indicate"),
]

_DIAGNOSTIC_RE = [(re.compile(p, re.IGNORECASE), r) for p, r in DIAGNOSTIC_PATTERNS]

# Red flag symptoms that should be highlighted in the summary
RED_FLAG_SYMPTOMS = [
    "chest pain",
    "shortness of breath",
    "sudden severe headache",
    "vision changes",
    "weakness on one side",
    "difficulty speaking",
    "blood in stool",
    "blood in urine",
    "unexplained weight loss",
    "fever over 103",
    "high fever",
    "neck stiffness with fever",
    "severe abdominal pain",
    "coughing blood",
    "hemoptysis",
]


def check_emergency(text: str) -> Tuple[bool, Optional[str]]:
    """
    Check if the patient's input contains emergency indicators.

    Returns:
        (is_emergency, matched_pattern) tuple
    """
    text_lower = text.lower()
    for pattern in _EMERGENCY_RE:
        match = pattern.search(text_lower)
        if match:
            matched = match.group()
            logger.critical(
                f"EMERGENCY DETECTED in patient input: '{matched}'"
            )
            return True, matched
    return False, None


def enforce_non_diagnostic(text: str) -> str:
    """
    Post-process assistant response to remove diagnostic language.

    Replaces diagnostic phrases with safe alternatives.
    """
    result = text
    for pattern, replacement in _DIAGNOSTIC_RE:
        if pattern.search(result):
            logger.warning(
                f"Diagnostic language detected in assistant response, replacing"
            )
            result = pattern.sub(replacement, result)
    return result


def check_red_flags(transcript: str) -> List[str]:
    """
    Scan the accumulated transcript for red flag symptoms.

    Returns list of matched red flag symptoms for clinician alert.
    """
    transcript_lower = transcript.lower()
    flags = []
    for symptom in RED_FLAG_SYMPTOMS:
        if symptom.lower() in transcript_lower:
            flags.append(symptom)
    return flags


# =====================================================
# Phase 2: PHI Redaction & Encryption for Conversations
# =====================================================

def redact_conversation_turns(turns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Redact PHI from conversation turns before persistence.

    Uses the existing compliance.redact_phi_text patterns (SSN, phone,
    email, DOB, MRN, insurance IDs, etc.).
    """
    from app.compliance import redact_phi_text

    redacted_turns = []
    for turn in turns:
        redacted = dict(turn)
        if "content" in redacted and isinstance(redacted["content"], str):
            redacted["content"] = redact_phi_text(redacted["content"])
        redacted_turns.append(redacted)
    return redacted_turns


def redact_conversation_transcript(transcript: str) -> str:
    """Redact PHI from the accumulated conversation transcript."""
    from app.compliance import redact_phi_text
    return redact_phi_text(transcript) if transcript else ""


def encrypt_conversation_data(data: str) -> Tuple[str, bool]:
    """
    Encrypt conversation data at rest if encryption is enabled.

    Returns (data_or_encrypted, is_encrypted) tuple.
    """
    if not settings.encryption_at_rest_enabled:
        return data, False

    try:
        from app.encryption import encrypt_data
        encrypted = encrypt_data(data)
        return encrypted, True
    except Exception as e:
        logger.error(f"Conversation encryption failed, storing unencrypted: {e}")
        return data, False


def decrypt_conversation_data(data: str, is_encrypted: bool) -> str:
    """Decrypt conversation data if it was encrypted at rest."""
    if not is_encrypted:
        return data

    try:
        from app.encryption import decrypt_data
        return decrypt_data(data)
    except Exception as e:
        logger.error(f"Conversation decryption failed: {e}")
        return data


# =====================================================
# Phase 2: Audit Logging for Conversation Events
# =====================================================

async def log_conversation_audit_event(
    event_type: str,
    session_id: str,
    details: Optional[str] = None,
    severity: str = "info",
):
    """
    Log a conversation event to the audit trail.

    Event types: conversation_started, conversation_ended,
    emergency_escalation, red_flag_detected, phi_accessed
    """
    if not settings.audit_logging_enabled:
        return

    try:
        from app.db.database import AsyncSessionLocal
        from app.db import crud

        async with AsyncSessionLocal() as db:
            await crud.create_audit_log(
                db=db,
                user_id=None,
                username=None,
                role=None,
                action=event_type,
                resource="conversation_session",
                resource_id=session_id,
                endpoint="/ws/conversation",
                http_method="WS",
                status_code=200,
                details=details,
                data_access_type="write" if event_type.endswith("_started") else "read",
                phi_accessed=event_type in ("phi_accessed", "emergency_escalation"),
            )
    except Exception as e:
        logger.error(f"Conversation audit log failed: {e}")


# =====================================================
# Phase 2: Enhanced Diagnostic Filtering
# =====================================================

# Additional treatment/dosage patterns to filter
TREATMENT_PATTERNS = [
    (re.compile(r"\btake\s+\d+\s*(?:mg|ml|tablet|pill|capsule)", re.IGNORECASE),
     "your doctor will advise on the appropriate dosage"),
    (re.compile(r"\b(?:recommend|suggest|advise)\s+(?:taking|using|trying)\b", re.IGNORECASE),
     "your doctor can discuss options with you"),
    (re.compile(r"\byou\s+(?:need|require)\s+(?:a|an|the)?\s*(?:surgery|operation|procedure)\b", re.IGNORECASE),
     "your doctor will determine the appropriate next steps"),
    (re.compile(r"\bstop\s+taking\b", re.IGNORECASE),
     "please consult your doctor before changing any medications"),
]


def enforce_treatment_safety(text: str) -> str:
    """
    Additional safety filter for treatment/dosage recommendations.

    Applied on top of enforce_non_diagnostic for extra coverage.
    """
    result = text
    for pattern, replacement in TREATMENT_PATTERNS:
        if pattern.search(result):
            logger.warning("Treatment recommendation detected in assistant response, replacing")
            result = pattern.sub(replacement, result)
    return result


def full_safety_filter(text: str) -> str:
    """
    Apply all safety filters to an assistant response.

    Combines non-diagnostic enforcement + treatment safety.
    """
    text = enforce_non_diagnostic(text)
    text = enforce_treatment_safety(text)
    return text
