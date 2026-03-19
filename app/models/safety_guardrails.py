"""
Safety Guardrails for the AI Voice Assistant.

Handles:
- Emergency detection (chest pain, breathing difficulty, suicidal ideation)
- Non-diagnostic language enforcement
- Red flag symptom alerts for clinician review
"""

import logging
import re
from typing import List, Optional, Tuple

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
