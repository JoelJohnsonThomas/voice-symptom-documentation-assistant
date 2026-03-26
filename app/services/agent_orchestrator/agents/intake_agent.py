"""
Intake Agent — Conversation flow, symptom collection, follow-up questions.

Replaces the core conversational loop in DialogueManager with an
agent-based approach that can be orchestrated alongside Safety,
Documentation, and Compliance agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.agent_orchestrator.state import (
    AgentMessage,
    AgentRole,
    AgentState,
)

logger = logging.getLogger(__name__)


class IntakeAgent:
    """Manages patient intake conversation flow.

    Responsibilities:
    - Collect chief complaint
    - Extract symptom details via follow-up questions
    - Determine when sufficient data exists for documentation
    - Merge NER entities into clinical context
    """

    def __init__(self):
        self._ner_service = None
        self._medgemma_service = None

    def _get_ner_service(self):
        if self._ner_service is None:
            try:
                from app.models.ner_service import get_ner_service
                self._ner_service = get_ner_service()
            except Exception as e:
                logger.warning(f"NER service unavailable: {e}")
        return self._ner_service

    def _get_medgemma_service(self):
        if self._medgemma_service is None:
            try:
                from app.models.medgemma_service import get_medgemma_service
                self._medgemma_service = get_medgemma_service()
            except Exception as e:
                logger.warning(f"MedGemma service unavailable: {e}")
        return self._medgemma_service

    async def process(self, state: AgentState) -> AgentState:
        """Process the current turn and update conversation context.

        Steps:
        1. Extract entities from user input via NER
        2. Update clinical context with new information
        3. Determine if follow-up questions are needed
        4. Generate response (acknowledgment or follow-up question)
        5. Signal readiness for documentation when sufficient data exists
        """
        user_input = state.current_input.strip()
        if not user_input:
            return state

        ctx = state.clinical_context
        state.turn_count += 1

        # Step 1: NER extraction
        entities = self._extract_entities(user_input)
        if entities:
            self._merge_entities(ctx, entities)

        # Step 2: Update transcript
        if ctx.transcript:
            ctx.transcript += f" {user_input}"
        else:
            ctx.transcript = user_input

        # Step 3: Determine conversation phase
        if not ctx.chief_complaint:
            # First substantive input — treat as chief complaint
            ctx.chief_complaint = user_input
            state.response_text = self._generate_acknowledgment(user_input, ctx)
            state.needs_followup = True

        elif state.needs_followup and len(ctx.followup_qa) < 3:
            # Receiving answer to a follow-up question
            if ctx.followup_qa:
                last_qa = ctx.followup_qa[-1]
                if not last_qa.get("answer"):
                    last_qa["answer"] = user_input

            # Generate next follow-up or move to documentation
            questions = self._generate_followup_questions(ctx)
            if questions:
                next_q = questions[0]
                ctx.followup_qa.append({"question": next_q, "answer": ""})
                state.response_text = next_q
                state.needs_followup = True
            else:
                state.needs_followup = False
                state.ready_for_documentation = True
                state.response_text = (
                    "Thank you for all that information. Let me prepare your "
                    "documentation now."
                )
        else:
            # Sufficient data collected
            state.ready_for_documentation = True
            state.response_text = (
                "I have enough information to generate your documentation."
            )

        # Step 4: Detect specialty from chief complaint
        try:
            from app.prompts.specialty import detect_specialty
            ctx.detected_specialty = detect_specialty(
                ctx.chief_complaint, ctx.patient_age
            )
        except Exception:
            pass

        # Step 5: Retrieve RAG context if ready for documentation
        if state.ready_for_documentation:
            self._retrieve_rag_context(ctx)

        state.completed_agents.append(AgentRole.INTAKE)
        return state

    def _extract_entities(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract medical entities using NER service."""
        ner = self._get_ner_service()
        if not ner or not ner.is_ready:
            return None
        try:
            entities = ner.extract_entities(text)
            vitals = ner.extract_vitals(text)
            return {"ner": entities, "vitals": vitals}
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return None

    def _merge_entities(self, ctx, entities: Dict[str, Any]) -> None:
        """Merge new entities into clinical context."""
        ner_data = entities.get("ner", {})
        for category in ("conditions", "medications"):
            existing_texts = {
                e.get("text", "").lower()
                for e in ctx.entities.get(category, [])
            }
            for entity in ner_data.get(category, []):
                if entity.get("text", "").lower() not in existing_texts:
                    ctx.entities.setdefault(category, []).append(entity)

        vitals_data = entities.get("vitals", {})
        for vital_name, vital_value in vitals_data.items():
            if vital_value is not None:
                ctx.vitals[vital_name] = vital_value

    def _generate_acknowledgment(self, complaint: str, ctx) -> str:
        """Generate an acknowledgment of the chief complaint."""
        return (
            f"I understand you're experiencing {complaint.lower().rstrip('.')}. "
            "Let me ask a few follow-up questions to help document this properly."
        )

    def _generate_followup_questions(self, ctx) -> list:
        """Generate follow-up questions using MedGemma."""
        medgemma = self._get_medgemma_service()
        if not medgemma:
            return []
        try:
            questions = medgemma.generate_follow_up_questions(
                ctx.transcript,
                detected_language=ctx.detected_language,
            )
            # Filter out already-asked questions
            asked = {qa["question"] for qa in ctx.followup_qa}
            return [q for q in questions if q not in asked]
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return []

    def _retrieve_rag_context(self, ctx) -> None:
        """Retrieve similar cases and clinical guidelines."""
        try:
            from app.models.rag_service import retrieve_similar_sessions
            results = retrieve_similar_sessions(ctx.transcript, top_k=3)
            ctx.rag_context = results
        except Exception as e:
            logger.debug(f"RAG retrieval skipped: {e}")
