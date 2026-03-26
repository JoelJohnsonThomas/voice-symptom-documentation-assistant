"""
Documentation Agent — SOAP generation, specialty templates, streaming output.

Generates structured clinical documentation from accumulated clinical
context. Integrates specialty templates, RAG grounding, and confidence
calibration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.services.agent_orchestrator.state import (
    AgentRole,
    AgentState,
    DocumentationResult,
)

logger = logging.getLogger(__name__)


class DocumentationAgent:
    """Generates SOAP documentation from clinical context.

    Responsibilities:
    - Select specialty template based on detected specialty
    - Construct prompt with context + entities
    - Generate SOAP via MedGemma (batch or streaming)
    - Run hallucination detection on output
    - Attach confidence scores
    """

    def __init__(self):
        self._medgemma = None

    def _get_medgemma(self):
        if self._medgemma is None:
            try:
                from app.models.medgemma_service import get_medgemma_service
                self._medgemma = get_medgemma_service()
            except Exception as e:
                logger.warning(f"MedGemma service unavailable: {e}")
        return self._medgemma

    async def process(self, state: AgentState) -> AgentState:
        """Generate SOAP documentation from clinical context.

        Only runs when state.ready_for_documentation is True and
        safety checks have passed.
        """
        if not state.ready_for_documentation:
            state.completed_agents.append(AgentRole.DOCUMENTATION)
            return state

        # Don't generate if safety flagged critical issues
        if state.safety_status.risk_level == "critical":
            logger.warning("Documentation skipped: critical safety issue")
            state.documentation = DocumentationResult(
                soap_subjective=f"Patient statement: {state.clinical_context.transcript}",
                soap_objective="Documentation withheld pending safety review.",
                soap_assessment="Documentation withheld pending safety review.",
                soap_plan="Documentation withheld pending safety review.",
            )
            state.completed_agents.append(AgentRole.DOCUMENTATION)
            return state

        ctx = state.clinical_context
        medgemma = self._get_medgemma()

        if not medgemma:
            state.documentation = self._fallback_documentation(ctx)
            state.completed_agents.append(AgentRole.DOCUMENTATION)
            return state

        try:
            # Generate full documentation via MedGemma
            result = medgemma.generate_documentation(
                transcript=ctx.transcript,
                detected_language=ctx.detected_language,
                similar_cases=ctx.rag_context or None,
                followup_qa=ctx.followup_qa or None,
                clinical_guidelines=ctx.clinical_guidelines or None,
                drug_interactions=ctx.drug_interactions or None,
                icd10_suggestions=ctx.icd10_suggestions or None,
            )

            state.documentation = DocumentationResult(
                soap_subjective=result.get("soap_note_subjective", ""),
                soap_objective=result.get("soap_note_objective", ""),
                soap_assessment=result.get("soap_note_assessment", ""),
                soap_plan=result.get("soap_note_plan", ""),
                confidence=result.get("field_confidence", {}),
                hallucination_check=result.get("hallucination_check", {}),
                specialty_template_used=ctx.detected_specialty,
            )

            # Run hallucination detection
            self._check_hallucination(state)

            logger.info(
                f"Documentation generated for session {state.session_id}, "
                f"specialty={ctx.detected_specialty}"
            )

        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            state.documentation = self._fallback_documentation(ctx)

        state.completed_agents.append(AgentRole.DOCUMENTATION)
        return state

    def _check_hallucination(self, state: AgentState) -> None:
        """Run hallucination detection on generated documentation."""
        try:
            from app.models.rag_evaluation_service import check_documentation_hallucination

            ctx = state.clinical_context
            doc_dict = {
                "soap_note_objective": state.documentation.soap_objective,
                "soap_note_assessment": state.documentation.soap_assessment,
                "soap_note_plan": state.documentation.soap_plan,
            }
            result = check_documentation_hallucination(
                documentation=doc_dict,
                similar_cases=ctx.rag_context,
                clinical_guidelines=ctx.clinical_guidelines,
                transcript=ctx.transcript,
            )
            state.documentation.hallucination_check = result
        except Exception as e:
            logger.debug(f"Hallucination check skipped: {e}")

    @staticmethod
    def _fallback_documentation(ctx) -> DocumentationResult:
        """Minimal documentation when MedGemma is unavailable."""
        return DocumentationResult(
            soap_subjective=f"Patient reports: {ctx.chief_complaint}. {ctx.transcript}",
            soap_objective="Pending clinician assessment.",
            soap_assessment="Pending clinician assessment.",
            soap_plan="Pending clinician assessment.",
        )
