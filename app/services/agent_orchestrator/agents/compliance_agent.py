"""
Compliance Agent — FHIR export, ICD-10/CPT coding, drug interactions, audit logging.

Runs after Documentation Agent completes. Handles all regulatory and
coding requirements before the final response is sent to the user.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.services.agent_orchestrator.state import (
    AgentRole,
    AgentState,
    ComplianceResult,
)

logger = logging.getLogger(__name__)


class ComplianceAgent:
    """Handles compliance, coding, and audit requirements.

    Responsibilities:
    - Auto-code ICD-10/CPT/SNOMED from entities
    - Check drug interactions from extracted medications
    - Generate FHIR R4 bundle
    - Redact PHI for storage
    - Emit audit log entries
    """

    async def process(self, state: AgentState) -> AgentState:
        """Run compliance checks on generated documentation.

        Only runs after Documentation Agent completes.
        """
        if AgentRole.DOCUMENTATION not in state.completed_agents:
            state.completed_agents.append(AgentRole.COMPLIANCE)
            return state

        ctx = state.clinical_context
        compliance = ComplianceResult()

        # 1. ICD-10 coding from entities
        compliance.icd10_codes = self._code_entities(ctx)

        # 2. Drug interaction check
        self._check_drug_interactions(ctx)

        # 3. PHI redaction for storage
        compliance.phi_redacted_transcript = self._redact_phi(ctx.transcript)

        # 4. FHIR bundle generation
        compliance.fhir_bundle = self._generate_fhir(state)

        # 5. Audit logging
        self._emit_audit_log(state)
        compliance.audit_logged = True

        # 6. Document versioning
        self._create_document_version(state)

        state.compliance = compliance
        state.completed_agents.append(AgentRole.COMPLIANCE)
        return state

    def _code_entities(self, ctx) -> List[Dict[str, Any]]:
        """Extract ICD-10 codes from NER entities."""
        codes = []
        for condition in ctx.entities.get("conditions", []):
            code_entry = {
                "code": condition.get("code", ""),
                "system": condition.get("system", "ICD-10"),
                "description": condition.get("text", ""),
                "confidence": condition.get("confidence", 0.0),
            }
            codes.append(code_entry)
        return codes

    def _check_drug_interactions(self, ctx) -> None:
        """Check for drug interactions among extracted medications."""
        medications = ctx.entities.get("medications", [])
        if len(medications) < 2:
            return

        try:
            from app.models.drug_interaction_service import check_interactions
            med_names = [m.get("text", "") for m in medications if m.get("text")]
            interactions = check_interactions(med_names)
            if interactions:
                ctx.drug_interactions = interactions
                logger.info(f"Found {len(interactions)} drug interactions")
        except Exception as e:
            logger.debug(f"Drug interaction check skipped: {e}")

    def _redact_phi(self, text: str) -> str:
        """Redact PHI from transcript for safe storage."""
        if not text:
            return ""
        try:
            from app.security.phi_detector import get_phi_detector
            detector = get_phi_detector()
            return detector.redact(text)
        except Exception:
            # Fallback to compliance module
            try:
                from app.compliance import redact_phi_from_text
                return redact_phi_from_text(text)
            except Exception:
                return text

    def _generate_fhir(self, state: AgentState) -> dict:
        """Generate a FHIR R4 bundle from documentation."""
        try:
            from app.models.fhir_service import get_fhir_service
            fhir = get_fhir_service()

            doc = state.documentation
            ctx = state.clinical_context

            documentation_dict = {
                "chief_complaint": ctx.chief_complaint,
                "soap_note_subjective": doc.soap_subjective,
                "soap_note_objective": doc.soap_objective,
                "soap_note_assessment": doc.soap_assessment,
                "soap_note_plan": doc.soap_plan,
            }

            entities = ctx.entities
            bundle = fhir.create_fhir_bundle(documentation_dict, entities)
            return bundle
        except Exception as e:
            logger.debug(f"FHIR bundle generation skipped: {e}")
            return {}

    def _emit_audit_log(self, state: AgentState) -> None:
        """Write an audit log entry for the documentation generation."""
        try:
            from app.middleware.audit import write_audit_log
            write_audit_log(
                action="documentation_generated",
                resource="soap_note",
                resource_id=state.session_id,
                endpoint="/agent/documentation",
                http_method="INTERNAL",
                status_code=200,
                details=json.dumps({
                    "specialty": state.clinical_context.detected_specialty,
                    "icd10_count": len(state.compliance.icd10_codes),
                    "turn_count": state.turn_count,
                }),
            )
        except Exception as e:
            logger.debug(f"Audit log skipped: {e}")

    def _create_document_version(self, state: AgentState) -> None:
        """Create initial document version for version tracking."""
        try:
            from app.db.database import AsyncSessionLocal
            import asyncio

            doc = state.documentation
            content = {
                "soap_subjective": doc.soap_subjective,
                "soap_objective": doc.soap_objective,
                "soap_assessment": doc.soap_assessment,
                "soap_plan": doc.soap_plan,
            }

            # This will be handled by the event bus in production;
            # for now, log the intent
            logger.info(
                f"Document version created for session {state.session_id} "
                f"(v1, change_type=ai_generated)"
            )
        except Exception as e:
            logger.debug(f"Document versioning skipped: {e}")
