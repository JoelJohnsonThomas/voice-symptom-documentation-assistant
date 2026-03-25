"""
Prompt Injection Detection & Output Validation

Defends against prompt injection attacks where malicious user input
(via transcript or follow-up answers) attempts to override LLM system
instructions, bypass safety guardrails, or extract sensitive information.

Defense layers:
1. Input scanning — detect injection patterns before they reach the LLM
2. Output validation — verify LLM output conforms to expected SOAP structure
3. Safety filter — reject outputs containing diagnostic or prescriptive language

References:
- OWASP LLM Top 10 (LLM01: Prompt Injection)
- Google AI Health Model Card guidelines
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Input Injection Detection
# ---------------------------------------------------------------------------

# Patterns that indicate prompt injection attempts.
# These are checked against user-provided text (transcripts, follow-up answers)
# BEFORE the text is interpolated into LLM prompts.

_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Direct instruction override
    (re.compile(r"(?:ignore|forget|disregard|override|bypass)\s+(?:all\s+)?(?:previous|prior|above|system|your)\s+(?:instructions?|prompts?|rules?|guidelines?|constraints?)", re.IGNORECASE),
     "instruction_override"),

    # Role manipulation
    (re.compile(r"(?:you\s+are\s+now|act\s+as|pretend\s+(?:to\s+be|you(?:'re|\s+are))|role\s*play\s+as|switch\s+to|enter\s+(?:\w+\s+)?mode)", re.IGNORECASE),
     "role_manipulation"),

    # System prompt extraction
    (re.compile(r"(?:reveal|show|print|output|display|repeat|echo)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|rules?|guidelines?|configuration)", re.IGNORECASE),
     "prompt_extraction"),

    # Delimiter / escape attacks
    (re.compile(r"```\s*(?:system|assistant|user)\b", re.IGNORECASE),
     "delimiter_escape"),
    (re.compile(r"<\|(?:system|im_start|im_end|endoftext)\|>", re.IGNORECASE),
     "special_token_injection"),

    # Instruction injection via fake formatting
    (re.compile(r"(?:NEW\s+INSTRUCTION|IMPORTANT\s*:|SYSTEM\s*:|ADMIN\s*:|OVERRIDE\s*:)\s", re.IGNORECASE),
     "fake_instruction_header"),

    # Jailbreak patterns
    (re.compile(r"(?:DAN|do\s+anything\s+now|developer\s+mode|jailbreak|unfiltered\s+mode)", re.IGNORECASE),
     "jailbreak_attempt"),

    # Data exfiltration
    (re.compile(r"(?:list\s+all\s+patients?|dump\s+(?:the\s+)?database|show\s+(?:all\s+)?records?|extract\s+(?:all\s+)?data)", re.IGNORECASE),
     "data_exfiltration"),

    # Diagnostic override — attempt to make the system diagnose
    (re.compile(r"(?:diagnose\s+(?:me|this|the\s+patient)|give\s+(?:me\s+)?a\s+diagnosis|what\s+(?:disease|condition)\s+do\s+I\s+have|prescribe\s+(?:me|a)\s+)", re.IGNORECASE),
     "diagnostic_override"),

    # Markdown/code injection to break output format
    (re.compile(r"(?:```(?:python|javascript|bash|sql|sh)\b)", re.IGNORECASE),
     "code_injection"),
]

# Maximum allowed input length (characters). Extremely long inputs
# are themselves a form of attack (context window stuffing).
MAX_INPUT_LENGTH = 10_000


@dataclass
class ScanResult:
    """Result of scanning user input for prompt injection."""
    is_safe: bool
    threats: list[dict] = field(default_factory=list)
    truncated: bool = False

    @property
    def threat_types(self) -> list[str]:
        return [t["type"] for t in self.threats]

    def summary(self) -> str:
        if self.is_safe:
            return "Input passed prompt injection scan."
        types = ", ".join(self.threat_types)
        return f"Prompt injection detected: {types}"


def scan_input(text: str) -> ScanResult:
    """Scan user-provided text for prompt injection patterns.

    Args:
        text: Raw user input (transcript, follow-up answer, etc.)

    Returns:
        ScanResult with is_safe=False if injection patterns are found.
    """
    if not text:
        return ScanResult(is_safe=True)

    threats: list[dict] = []
    truncated = False

    # Length check
    if len(text) > MAX_INPUT_LENGTH:
        truncated = True
        threats.append({
            "type": "excessive_length",
            "detail": f"Input length {len(text)} exceeds maximum {MAX_INPUT_LENGTH}",
        })

    # Pattern matching
    for pattern, threat_type in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            threats.append({
                "type": threat_type,
                "detail": f"Matched pattern near position {match.start()}",
                "matched_text": match.group()[:50],  # Truncate for logging
            })

    is_safe = len(threats) == 0

    if not is_safe:
        logger.warning(
            "Prompt injection detected",
            extra={
                "threat_count": len(threats),
                "threat_types": [t["type"] for t in threats],
            },
        )

    return ScanResult(is_safe=is_safe, threats=threats, truncated=truncated)


def sanitize_input(text: str) -> str:
    """Sanitize user input by neutralizing common injection vectors.

    This is a softer alternative to outright rejection — it strips
    known dangerous patterns while preserving legitimate clinical content.
    Use this when you want to allow the input but reduce risk.

    Args:
        text: Raw user input.

    Returns:
        Sanitized text with injection patterns neutralized.
    """
    if not text:
        return text

    sanitized = text

    # Remove special tokens that could confuse the model
    sanitized = re.sub(r"<\|[^>]*\|>", "", sanitized)

    # Remove markdown code fences
    sanitized = re.sub(r"```\w*\n?", "", sanitized)

    # Remove fake instruction headers
    sanitized = re.sub(
        r"^(NEW INSTRUCTION|IMPORTANT|SYSTEM|ADMIN|OVERRIDE)\s*:\s*",
        "",
        sanitized,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Truncate to max length
    if len(sanitized) > MAX_INPUT_LENGTH:
        sanitized = sanitized[:MAX_INPUT_LENGTH]

    return sanitized.strip()


# ---------------------------------------------------------------------------
# 2. Output Validation
# ---------------------------------------------------------------------------

# Expected SOAP section headers in the LLM output
_SOAP_SECTIONS = {"OBJECTIVE", "ASSESSMENT", "PLAN"}
_SUBJECTIVE_FIELDS = {
    "symptoms", "location", "quality", "duration", "severity",
    "associated", "soap", "chief_complaint",
}

# Patterns that indicate the model produced unsafe output
_UNSAFE_OUTPUT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Definitive diagnosis
    (re.compile(r"(?:you\s+have|diagnosis\s*(?:is|:)\s*\w|confirmed?\s+diagnosis|definitive(?:ly)?\s+diagnos)", re.IGNORECASE),
     "definitive_diagnosis"),

    # Direct prescription
    (re.compile(r"(?:take\s+\d+\s*mg|prescri(?:be|ption)\s*:\s*\w|I\s+(?:am\s+)?prescribing|start(?:ing)?\s+(?:you\s+on|treatment\s+with)\s+\w+\s+\d+\s*mg)", re.IGNORECASE),
     "direct_prescription"),

    # Dosage recommendation
    (re.compile(r"\b\d+\s*(?:mg|mcg|ml|units?)\s+(?:once|twice|three\s+times|daily|every\s+\d+\s+hours?|q\d+h|bid|tid|qid|prn)\b", re.IGNORECASE),
     "dosage_recommendation"),

    # Surgical recommendation
    (re.compile(r"(?:you\s+(?:need|require|should\s+(?:have|get|undergo))\s+(?:surgery|an?\s+operation|the\s+procedure))", re.IGNORECASE),
     "surgical_recommendation"),

    # Prompt leak — model echoed back system instructions
    (re.compile(r"(?:my\s+(?:system\s+)?instructions?\s+(?:are|say|tell)|I\s+was\s+(?:told|instructed|programmed)\s+to)", re.IGNORECASE),
     "prompt_leak"),
]


@dataclass
class OutputValidationResult:
    """Result of validating LLM output."""
    is_valid: bool
    is_safe: bool
    issues: list[str] = field(default_factory=list)
    safety_violations: list[dict] = field(default_factory=list)


def validate_soap_output(output: str) -> OutputValidationResult:
    """Validate that LLM output conforms to expected SOAP structure and safety.

    Args:
        output: Raw LLM-generated text.

    Returns:
        OutputValidationResult with structural and safety assessments.
    """
    issues: list[str] = []
    safety_violations: list[dict] = []

    if not output or not output.strip():
        return OutputValidationResult(
            is_valid=False, is_safe=True, issues=["Empty output"]
        )

    # Structural validation: check for expected SOAP section headers
    text_upper = output.upper()
    missing_sections = []
    for section in _SOAP_SECTIONS:
        # Look for "OBJECTIVE:" or "OBJECTIVE\n" patterns
        if not re.search(rf"\b{section}\s*:", text_upper):
            missing_sections.append(section)

    if missing_sections:
        issues.append(f"Missing SOAP sections: {', '.join(missing_sections)}")

    # Safety validation: check for unsafe language
    for pattern, violation_type in _UNSAFE_OUTPUT_PATTERNS:
        match = pattern.search(output)
        if match:
            safety_violations.append({
                "type": violation_type,
                "matched_text": match.group()[:80],
            })

    is_valid = len(missing_sections) == 0
    is_safe = len(safety_violations) == 0

    if not is_safe:
        logger.warning(
            "Unsafe LLM output detected",
            extra={
                "violation_count": len(safety_violations),
                "violation_types": [v["type"] for v in safety_violations],
            },
        )

    return OutputValidationResult(
        is_valid=is_valid,
        is_safe=is_safe,
        issues=issues,
        safety_violations=safety_violations,
    )


def validate_subjective_output(output: str) -> OutputValidationResult:
    """Validate the subjective/extraction output from the first LLM pass.

    Lighter validation since the output format is less structured.
    """
    safety_violations: list[dict] = []

    if not output or not output.strip():
        return OutputValidationResult(
            is_valid=False, is_safe=True, issues=["Empty output"]
        )

    # Safety check only — structure is more flexible for extraction
    for pattern, violation_type in _UNSAFE_OUTPUT_PATTERNS:
        match = pattern.search(output)
        if match:
            safety_violations.append({
                "type": violation_type,
                "matched_text": match.group()[:80],
            })

    return OutputValidationResult(
        is_valid=True,
        is_safe=len(safety_violations) == 0,
        issues=[],
        safety_violations=safety_violations,
    )
