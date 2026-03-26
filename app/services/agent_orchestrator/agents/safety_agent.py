"""
Safety Agent — Emergency detection, PHI scan, prompt injection, output validation.

Runs in parallel with Intake on every turn. Blocks or modifies pipeline
execution if critical safety issues are detected.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.services.agent_orchestrator.state import (
    AgentRole,
    AgentState,
    SafetyStatus,
)

logger = logging.getLogger(__name__)


class SafetyAgent:
    """Evaluates safety of user input and generated output.

    Responsibilities:
    - Emergency symptom detection (triggers escalation)
    - Red flag symptom screening
    - PHI detection and location tracking
    - Prompt injection detection
    - Output validation (SOAP structure + safety language)
    """

    async def process(self, state: AgentState) -> AgentState:
        """Run all safety checks on the current input.

        This agent runs in parallel with Intake Agent on every turn.
        """
        user_input = state.current_input.strip()
        if not user_input:
            state.completed_agents.append(AgentRole.SAFETY)
            return state

        safety = SafetyStatus()

        # 1. Emergency detection
        emergency = self._check_emergency(user_input)
        if emergency:
            safety.is_emergency = True
            safety.emergency_type = emergency.get("type", "unknown")
            safety.risk_level = "critical"
            logger.warning(
                f"EMERGENCY detected in session {state.session_id}: "
                f"{safety.emergency_type}"
            )

        # 2. Red flag screening
        red_flags = self._check_red_flags(user_input)
        if red_flags:
            safety.red_flags = red_flags
            if safety.risk_level != "critical":
                safety.risk_level = "high"

        # 3. Prompt injection detection
        injection = self._check_prompt_injection(user_input)
        if injection.get("is_injection"):
            safety.prompt_injection_detected = True
            safety.injection_details = injection.get("details", "")
            safety.risk_level = "critical"
            logger.warning(
                f"Prompt injection detected in session {state.session_id}: "
                f"{safety.injection_details}"
            )

        # 4. PHI detection
        phi_result = self._detect_phi(user_input)
        if phi_result.get("phi_found"):
            safety.phi_detected = True
            safety.phi_locations = phi_result.get("locations", [])

        state.safety_status = safety

        # If emergency, override response
        if safety.is_emergency:
            state.response_text = self._get_emergency_response(safety.emergency_type)
            state.is_final = True

        state.completed_agents.append(AgentRole.SAFETY)
        return state

    async def validate_output(self, state: AgentState) -> AgentState:
        """Validate generated documentation output for safety.

        Runs after Documentation Agent completes.
        """
        doc = state.documentation
        if not doc.soap_assessment and not doc.soap_plan:
            return state

        # Check output for unsafe language
        for section_name, section_text in [
            ("assessment", doc.soap_assessment),
            ("plan", doc.soap_plan),
        ]:
            if not section_text:
                continue
            validation = self._validate_output_text(section_text)
            if not validation.get("is_safe"):
                logger.warning(
                    f"Output validation failed for {section_name}: "
                    f"{validation.get('reason')}"
                )
                state.response_metadata[f"{section_name}_safety_warning"] = (
                    validation.get("reason")
                )

        return state

    def _check_emergency(self, text: str) -> dict:
        """Check for emergency symptoms using safety guardrails."""
        try:
            from app.models.safety_guardrails import check_emergency
            return check_emergency(text) or {}
        except Exception:
            return {}

    def _check_red_flags(self, text: str) -> List[str]:
        """Screen for red flag symptoms."""
        try:
            from app.models.safety_guardrails import check_red_flags
            flags = check_red_flags(text)
            return flags if isinstance(flags, list) else []
        except Exception:
            return []

    def _check_prompt_injection(self, text: str) -> dict:
        """Scan input for prompt injection attempts."""
        try:
            from app.security.prompt_guard import scan_input
            result = scan_input(text)
            return {
                "is_injection": result.is_injection,
                "details": ", ".join(
                    m.pattern_name for m in (result.matches or [])
                ) if hasattr(result, "matches") and result.matches else "",
            }
        except Exception:
            return {"is_injection": False}

    def _detect_phi(self, text: str) -> dict:
        """Detect PHI in user input."""
        try:
            from app.security.phi_detector import get_phi_detector
            detector = get_phi_detector()
            scan = detector.scan(text)
            return {
                "phi_found": scan.has_phi,
                "locations": [
                    {"type": e.entity_type, "start": e.start, "end": e.end}
                    for e in (scan.entities or [])
                ] if hasattr(scan, "entities") and scan.entities else [],
            }
        except Exception:
            return {"phi_found": False}

    def _validate_output_text(self, text: str) -> dict:
        """Validate generated output for unsafe language."""
        try:
            from app.security.prompt_guard import validate_soap_output
            result = validate_soap_output(text)
            return {
                "is_safe": result.is_safe,
                "reason": result.reason if hasattr(result, "reason") else "",
            }
        except Exception:
            return {"is_safe": True}

    @staticmethod
    def _get_emergency_response(emergency_type: str) -> str:
        """Generate emergency escalation response."""
        return (
            "I've detected symptoms that may require immediate medical attention. "
            "Please call emergency services (911) or go to the nearest emergency room "
            "immediately. This system cannot provide emergency medical care. "
            f"Concern flagged: {emergency_type}."
        )
