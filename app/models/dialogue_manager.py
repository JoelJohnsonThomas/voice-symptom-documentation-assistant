"""
Dialogue Manager — State machine orchestrating the AI Voice Assistant conversation.

Manages conversation flow through states:
GREETING → CHIEF_COMPLAINT → SYMPTOM_DETAILS → FOLLOW_UP → SUMMARY → ENDED

Phase 1: Core conversational loop with NER, RAG, MedGemma integration.
Phase 2: RAG-grounded responses, hallucination check, enhanced clinician mode,
         full safety filtering, PHI redaction, audit logging.
"""

import json
import logging
import random
from typing import Any, Dict, Optional

from app.config import settings
from app.models.conversation_session import (
    AssistantResponse,
    ConversationMode,
    ConversationSessionData,
    ConversationState,
)
from app.models.safety_guardrails import (
    check_emergency,
    check_red_flags,
    full_safety_filter,
    log_conversation_audit_event,
    redact_conversation_transcript,
    redact_conversation_turns,
)
from app.prompts.conversation_prompts import (
    ACKNOWLEDGMENT_TEMPLATES,
    CLINICIAN_SYSTEM_PROMPT,
    CONVERSATION_RAG_SYSTEM_PROMPT,
    CONVERSATION_SOAP_PROMPT,
    CONVERSATION_SYSTEM_PROMPT,
    EMERGENCY_RESPONSE,
    FOLLOWUP_GENERATION_PROMPT,
    GREETING_CLINICIAN,
    GREETING_PATIENT,
    SESSION_END,
    SUMMARY_INTRO,
    SYMPTOM_ACK_TEMPLATE,
    TRANSITION_TO_FOLLOWUP,
    get_acknowledgment_for_language,
    get_emergency_for_language,
    get_greeting_for_language,
    get_summary_for_language,
)

logger = logging.getLogger(__name__)


class DialogueManager:
    """
    Manages conversation state and turn processing for a single session.

    Each WebSocket connection gets its own DialogueManager instance.
    """

    def __init__(self, mode: ConversationMode = ConversationMode.PATIENT,
                 language: str = "en"):
        self.session = ConversationSessionData(mode=mode, language=language)
        self._ner_service = None
        self._medgemma_service = None
        self._rag_service = None
        self._questions_asked: list[str] = []

    async def get_greeting(self) -> AssistantResponse:
        """Generate the initial greeting message (Phase 3: multi-language)."""
        if self.session.mode == ConversationMode.CLINICIAN:
            text = GREETING_CLINICIAN
        else:
            text = get_greeting_for_language(
                self.session.language, self.session.mode.value
            )

        self.session.add_turn("assistant", text)
        self.session.state = ConversationState.CHIEF_COMPLAINT

        # Phase 2: Audit log conversation start
        await log_conversation_audit_event(
            event_type="conversation_started",
            session_id=self.session.session_id,
            details=f"mode={self.session.mode.value}, language={self.session.language}",
        )

        return AssistantResponse(
            text=text,
            state=ConversationState.CHIEF_COMPLAINT,
            previous_state=ConversationState.GREETING,
        )

    async def process_input(self, user_text: str) -> AssistantResponse:
        """
        Process user input and return the assistant's response.

        Routes to the appropriate handler based on current state.
        """
        if not user_text or not user_text.strip():
            return AssistantResponse(
                text="I didn't catch that. Could you please repeat?",
                state=self.session.state,
            )

        # Record user turn
        self.session.add_turn("user", user_text)

        # Emergency check (all states)
        is_emergency, matched = check_emergency(user_text)
        if is_emergency:
            return await self._handle_emergency(matched)

        # Check for end-of-conversation signals
        if self._is_end_signal(user_text):
            return await self._handle_summary()

        # Route by state
        state = self.session.state
        if state == ConversationState.CHIEF_COMPLAINT:
            return await self._handle_chief_complaint(user_text)
        elif state == ConversationState.SYMPTOM_DETAILS:
            return await self._handle_symptom_details(user_text)
        elif state == ConversationState.FOLLOW_UP:
            return await self._handle_follow_up(user_text)
        elif state == ConversationState.SUMMARY:
            return await self._handle_summary()
        elif state == ConversationState.ENDED:
            return AssistantResponse(
                text=SESSION_END,
                state=ConversationState.ENDED,
                is_final=True,
            )
        else:
            # Clinician mode or fallback
            if self.session.mode == ConversationMode.CLINICIAN:
                return await self._handle_clinician_query(user_text)
            return AssistantResponse(
                text="I'm not sure how to help with that. Could you rephrase?",
                state=self.session.state,
            )

    async def _handle_emergency(self, matched_pattern: Optional[str]) -> AssistantResponse:
        """Handle emergency detection — advise 911 immediately (Phase 3: multi-lang)."""
        emergency_text = get_emergency_for_language(self.session.language)
        self.session.state = ConversationState.EMERGENCY_ESCALATION
        self.session.add_turn("assistant", emergency_text)

        # Phase 2: Audit log the emergency escalation
        await log_conversation_audit_event(
            event_type="emergency_escalation",
            session_id=self.session.session_id,
            details=f"Emergency pattern matched: {matched_pattern}",
            severity="critical",
        )

        return AssistantResponse(
            text=emergency_text,
            state=ConversationState.EMERGENCY_ESCALATION,
            is_emergency=True,
            is_final=True,
        )

    async def _handle_chief_complaint(self, user_text: str) -> AssistantResponse:
        """Process the initial chief complaint (Phase 3: auto-detect language)."""
        # Phase 3: Auto-detect language from first utterance
        if settings.conversation_auto_detect_language:
            detected_lang = await self._detect_language(user_text)
            if detected_lang and detected_lang != self.session.language:
                self.session.language = detected_lang
                logger.info(f"Language auto-detected: {detected_lang}")

        # Run NER to extract entities
        entities = await self._run_ner(user_text)

        # Build acknowledgment with extracted symptoms (Phase 3: multi-lang)
        ack_templates = get_acknowledgment_for_language(self.session.language)
        symptom_names = [e.get("text", e.get("name", "")) for e in entities.get("conditions", [])]
        if symptom_names:
            summary = ", ".join(symptom_names[:3])
            text = SYMPTOM_ACK_TEMPLATE.format(symptom_summary=summary)
        else:
            text = random.choice(ack_templates)

        # Transition to symptom details
        text += " " + TRANSITION_TO_FOLLOWUP
        prev_state = self.session.state
        self.session.state = ConversationState.SYMPTOM_DETAILS
        self.session.add_turn("assistant", text)

        return AssistantResponse(
            text=text,
            state=ConversationState.SYMPTOM_DETAILS,
            previous_state=prev_state,
            entities_update=entities,
        )

    async def _handle_symptom_details(self, user_text: str) -> AssistantResponse:
        """Gather more symptom details, then transition to follow-up."""
        # Run NER
        entities = await self._run_ner(user_text)

        # Acknowledge (Phase 3: multi-lang)
        ack_templates = get_acknowledgment_for_language(self.session.language)
        text = random.choice(ack_templates)

        # Transition to follow-up (LLM-generated questions)
        prev_state = self.session.state
        self.session.state = ConversationState.FOLLOW_UP
        self.session.followup_round = 0

        # Trigger RAG retrieval for context (cached for session)
        await self._fetch_rag_context()

        # Generate first follow-up question
        followup = await self._generate_followup_question()
        if followup:
            # Phase 2: Apply safety filter to LLM output
            followup = full_safety_filter(followup)
            text += " " + followup

        self.session.add_turn("assistant", text)

        has_rag = (self.session.rag_context is not None
                   and self.session.rag_context.get("has_context", False))

        return AssistantResponse(
            text=text,
            state=ConversationState.FOLLOW_UP,
            previous_state=prev_state,
            entities_update=entities,
            rag_grounded=has_rag,
        )

    async def _handle_follow_up(self, user_text: str) -> AssistantResponse:
        """Process follow-up answers and ask more questions or summarize."""
        # Run NER
        entities = await self._run_ner(user_text)

        self.session.followup_round += 1

        # Check if we've done enough follow-up rounds
        max_rounds = settings.conversation_followup_rounds
        if self.session.followup_round >= max_rounds:
            return await self._handle_summary()

        # Generate next follow-up question (Phase 2: RAG-grounded, Phase 3: multi-lang)
        ack_templates = get_acknowledgment_for_language(self.session.language)
        text = random.choice(ack_templates)
        followup = await self._generate_followup_question()
        if followup:
            # Phase 2: Apply safety filter to LLM-generated text
            followup = full_safety_filter(followup)
            text += " " + followup
        else:
            # No more questions to ask — summarize
            return await self._handle_summary()

        self.session.add_turn("assistant", text)

        has_rag = (self.session.rag_context is not None
                   and self.session.rag_context.get("has_context", False))

        return AssistantResponse(
            text=text,
            state=ConversationState.FOLLOW_UP,
            entities_update=entities,
            rag_grounded=has_rag,
        )

    async def _handle_summary(self) -> AssistantResponse:
        """Generate SOAP documentation from the conversation."""
        prev_state = self.session.state
        self.session.state = ConversationState.SUMMARY

        # Generate documentation
        documentation = await self._generate_documentation()

        # Check for red flags
        red_flags = check_red_flags(self.session.accumulated_transcript)
        if red_flags:
            documentation["red_flags"] = red_flags
            # Phase 2: Audit log red flags
            await log_conversation_audit_event(
                event_type="red_flag_detected",
                session_id=self.session.session_id,
                details=f"Red flags: {', '.join(red_flags)}",
                severity="warning",
            )

        # Phase 2: Run hallucination check on generated SOAP
        hallucination_result = await self._run_hallucination_check(documentation)
        if hallucination_result:
            documentation["hallucination_check"] = hallucination_result

        # Phase 2: Enrich with ICD-10 codes and drug interactions
        enrichment = await self._enrich_documentation()
        if enrichment.get("icd10_suggestions"):
            documentation["icd10_suggestions"] = enrichment["icd10_suggestions"]
        if enrichment.get("drug_interactions"):
            documentation["drug_interactions"] = enrichment["drug_interactions"]

        text = get_summary_for_language(self.session.language)
        self.session.add_turn("assistant", text)
        self.session.state = ConversationState.ENDED

        # Phase 2: Audit log conversation end
        await log_conversation_audit_event(
            event_type="conversation_ended",
            session_id=self.session.session_id,
            details=f"turns={len(self.session.turns)}, red_flags={len(red_flags)}",
        )

        return AssistantResponse(
            text=text,
            state=ConversationState.ENDED,
            previous_state=prev_state,
            is_final=True,
            documentation=documentation,
        )

    async def _handle_clinician_query(self, user_text: str) -> AssistantResponse:
        """Handle clinician hands-free queries with intent classification."""
        text_lower = user_text.lower()

        # Phase 2: Enhanced intent classification with broader keyword coverage
        intent = self._classify_clinician_intent(text_lower)

        if intent == "drug_interaction":
            result = await self._query_drug_interactions(user_text)
        elif intent == "icd10":
            result = await self._query_icd10(user_text)
        elif intent == "similar_cases":
            result = await self._query_similar_cases(user_text)
        elif intent == "guidelines":
            result = await self._query_guidelines(user_text)
        else:
            result = (
                "I can help with:\n"
                "- Drug interactions (e.g., 'check interactions between metformin and lisinopril')\n"
                "- ICD-10 codes (e.g., 'ICD-10 for persistent cough')\n"
                "- Similar cases (e.g., 'find similar cases to chest pain with dyspnea')\n"
                "- Clinical guidelines (e.g., 'guidelines for hypertension management')\n"
                "What would you like to know?"
            )

        self.session.add_turn("assistant", result)

        return AssistantResponse(
            text=result,
            state=self.session.state,
        )

    @staticmethod
    def _classify_clinician_intent(text_lower: str) -> str:
        """Classify clinician query intent via keyword matching."""
        drug_keywords = [
            "drug interaction", "interaction between", "interact with",
            "contraindic", "drug-drug", "medication interaction",
            "safe to combine", "combine with", "taken together",
        ]
        icd_keywords = [
            "icd-10", "icd10", "icd code", "diagnosis code",
            "billing code", "code for", "classification code",
        ]
        case_keywords = [
            "similar case", "similar patient", "past case",
            "previous patient", "case like", "seen before",
        ]
        guideline_keywords = [
            "guideline", "protocol", "standard of care",
            "best practice", "recommendation for", "management of",
        ]

        for kw in drug_keywords:
            if kw in text_lower:
                return "drug_interaction"
        for kw in icd_keywords:
            if kw in text_lower:
                return "icd10"
        for kw in case_keywords:
            if kw in text_lower:
                return "similar_cases"
        for kw in guideline_keywords:
            if kw in text_lower:
                return "guidelines"

        return "unknown"

    # =====================================================
    # Service integration helpers
    # =====================================================

    async def _run_ner(self, text: str) -> Dict[str, Any]:
        """Run NER extraction and merge into session entities."""
        try:
            if self._ner_service is None:
                from app.models.ner_service import get_ner_service
                self._ner_service = get_ner_service()

            import asyncio
            loop = asyncio.get_event_loop()
            entities = await loop.run_in_executor(
                None, self._ner_service.extract_entities, text
            )

            # Merge into session
            for key in ["conditions", "medications"]:
                existing_texts = {
                    e.get("text", e.get("name", "")).lower()
                    for e in self.session.extracted_entities.get(key, [])
                }
                for entity in entities.get(key, []):
                    entity_text = entity.get("text", entity.get("name", "")).lower()
                    if entity_text not in existing_texts:
                        self.session.extracted_entities[key].append(entity)

            return entities
        except Exception as e:
            logger.warning(f"NER extraction failed: {e}")
            return {"conditions": [], "medications": []}

    async def _generate_followup_question(self) -> Optional[str]:
        """Generate a follow-up question using MedGemma."""
        try:
            if self._medgemma_service is None:
                from app.models.medgemma_service import get_medgemma_service
                self._medgemma_service = get_medgemma_service()

            if self._medgemma_service is None or not self._medgemma_service.is_ready:
                return self._get_fallback_question()

            import asyncio
            loop = asyncio.get_event_loop()

            # Use existing follow-up generation
            questions = await loop.run_in_executor(
                None,
                self._medgemma_service.generate_followup_questions,
                self.session.accumulated_transcript,
                self.session.language,
            )

            # Filter out already-asked questions
            for q in questions:
                if q not in self._questions_asked:
                    self._questions_asked.append(q)
                    return q

            return None  # No new questions
        except Exception as e:
            logger.warning(f"Follow-up generation failed: {e}")
            return self._get_fallback_question()

    def _get_fallback_question(self) -> str:
        """Return a generic follow-up question when LLM is unavailable."""
        fallbacks = [
            "How long have you been experiencing these symptoms?",
            "On a scale of 1 to 10, how would you rate the severity?",
            "Is there anything that makes it better or worse?",
            "Have you noticed any other symptoms alongside this?",
            "Are you currently taking any medications?",
        ]
        for q in fallbacks:
            if q not in self._questions_asked:
                self._questions_asked.append(q)
                return q
        return "Is there anything else you'd like to share with your doctor?"

    async def _generate_documentation(self) -> Dict[str, Any]:
        """Generate SOAP documentation from the conversation."""
        try:
            if self._medgemma_service is None:
                from app.models.medgemma_service import get_medgemma_service
                self._medgemma_service = get_medgemma_service()

            if self._medgemma_service is None or not self._medgemma_service.is_ready:
                return self._build_fallback_documentation()

            import asyncio
            loop = asyncio.get_event_loop()

            result = await loop.run_in_executor(
                None,
                self._medgemma_service.generate_documentation,
                self.session.accumulated_transcript,
            )

            if result and isinstance(result, dict):
                return result

            return self._build_fallback_documentation()
        except Exception as e:
            logger.error(f"Documentation generation failed: {e}")
            return self._build_fallback_documentation()

    def _build_fallback_documentation(self) -> Dict[str, Any]:
        """Build basic documentation from extracted entities when LLM is unavailable."""
        conditions = [
            e.get("text", e.get("name", ""))
            for e in self.session.extracted_entities.get("conditions", [])
        ]
        medications = [
            e.get("text", e.get("name", ""))
            for e in self.session.extracted_entities.get("medications", [])
        ]

        return {
            "chief_complaint": conditions[0] if conditions else "See transcript",
            "subjective": self.session.accumulated_transcript,
            "objective": "No objective measurements recorded during intake.",
            "assessment": "Requires clinician review. Extracted conditions: " + ", ".join(conditions) if conditions else "Requires clinician review.",
            "plan": "Clinician to review transcript and extracted entities.",
            "extracted_conditions": conditions,
            "extracted_medications": medications,
            "confidence": {
                "chief_complaint": "medium" if conditions else "low",
                "subjective": "high",
                "objective": "low",
                "assessment": "low",
                "plan": "low",
            },
            "requires_clinician_review": True,
        }

    async def _fetch_rag_context(self):
        """Fetch RAG context for grounding follow-up questions."""
        if self.session.rag_context is not None:
            return  # Already cached

        if not settings.rag_enabled:
            return

        try:
            from app.models import rag_service
            context = await rag_service.retrieve_enriched_context(
                self.session.accumulated_transcript
            )
            if context:
                self.session.rag_context = context
        except Exception as e:
            logger.warning(f"RAG context retrieval failed: {e}")

    async def _query_drug_interactions(self, query: str) -> str:
        """Query drug interaction service for clinician mode."""
        try:
            from app.models import drug_interaction_service
            # Extract medication names from query
            medications = [
                e.get("text", "")
                for e in (await self._run_ner(query)).get("medications", [])
            ]
            if len(medications) >= 2:
                result = drug_interaction_service.check_interactions(medications)
                if result:
                    return f"Drug interaction check results: {json.dumps(result, indent=2)}"
            return "I need at least two medication names to check interactions. Could you specify them?"
        except Exception as e:
            logger.error(f"Drug interaction query failed: {e}")
            return "I wasn't able to check drug interactions at this time. Please try again."

    async def _query_icd10(self, query: str) -> str:
        """Query ICD-10 lookup for clinician mode."""
        try:
            from app.models import icd10_service
            # Extract condition from query
            conditions = [
                e.get("text", "")
                for e in (await self._run_ner(query)).get("conditions", [])
            ]
            if conditions:
                results = []
                for condition in conditions[:3]:
                    codes = icd10_service.lookup_icd10_codes(condition)
                    if codes:
                        formatted = ", ".join(
                            f"{c.get('code', '?')} ({c.get('description', '?')}, score={c.get('score', 0):.2f})"
                            for c in codes[:3]
                        )
                        results.append(f"{condition}: {formatted}")
                if results:
                    return "ICD-10 suggestions:\n" + "\n".join(results)
            return "Could you specify the condition you'd like ICD-10 codes for?"
        except Exception as e:
            logger.error(f"ICD-10 query failed: {e}")
            return "I wasn't able to look up ICD-10 codes at this time."

    async def _query_similar_cases(self, query: str) -> str:
        """Query RAG for similar cases in clinician mode."""
        try:
            from app.models import rag_service
            results = rag_service.retrieve_similar_sessions(query)
            if results:
                summaries = []
                for i, case in enumerate(results[:3], 1):
                    doc = case.get("document", "")[:200]
                    score = case.get("score", 0)
                    summaries.append(f"  {i}. (similarity={score:.2f}) {doc}...")
                return f"Found {len(results)} similar cases:\n" + "\n".join(summaries)
            return "No similar cases found in the knowledge base."
        except Exception as e:
            logger.error(f"Similar case query failed: {e}")
            return "I wasn't able to search for similar cases at this time."

    async def _query_guidelines(self, query: str) -> str:
        """Query knowledge base for clinical guidelines (Phase 2)."""
        try:
            from app.models.knowledge_base_service import retrieve_guidelines
            results = retrieve_guidelines(query)
            if results:
                summaries = []
                for i, g in enumerate(results[:3], 1):
                    doc = g.get("document", "")[:300]
                    score = g.get("score", 0)
                    summaries.append(f"  {i}. (relevance={score:.2f}) {doc}...")
                return f"Found {len(results)} relevant guidelines:\n" + "\n".join(summaries)
            return "No matching clinical guidelines found."
        except Exception as e:
            logger.error(f"Guidelines query failed: {e}")
            return "I wasn't able to search clinical guidelines at this time."

    # =====================================================
    # Phase 2: Hallucination Check & Documentation Enrichment
    # =====================================================

    async def _run_hallucination_check(self, documentation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run hallucination check on generated SOAP using RAG evidence."""
        if not settings.rag_hallucination_check_enabled:
            return None

        if not self.session.rag_context:
            return None

        try:
            from app.models import rag_evaluation_service
            result = rag_evaluation_service.check_documentation_hallucination(
                documentation=documentation,
                similar_cases=self.session.rag_context.get("similar_sessions", []),
                clinical_guidelines=self.session.rag_context.get("clinical_guidelines", []),
                transcript=self.session.accumulated_transcript,
            )
            return result
        except Exception as e:
            logger.warning(f"Hallucination check failed: {e}")
            return None

    async def _enrich_documentation(self) -> Dict[str, Any]:
        """Enrich documentation with ICD-10 codes and drug interaction checks."""
        enrichment: Dict[str, Any] = {}

        # ICD-10 enrichment from extracted conditions
        if settings.icd10_lookup_enabled:
            try:
                from app.models import icd10_service
                conditions = [
                    e.get("text", e.get("name", ""))
                    for e in self.session.extracted_entities.get("conditions", [])
                ]
                all_codes = []
                for condition in conditions[:5]:
                    codes = icd10_service.lookup_icd10_codes(condition)
                    if codes:
                        all_codes.append({
                            "symptom": condition,
                            "codes": codes[:3],
                        })
                if all_codes:
                    enrichment["icd10_suggestions"] = all_codes
            except Exception as e:
                logger.warning(f"ICD-10 enrichment failed: {e}")

        # Drug interaction enrichment from extracted medications
        if settings.drug_interaction_check_enabled:
            try:
                from app.models import drug_interaction_service
                medications = [
                    e.get("text", e.get("name", ""))
                    for e in self.session.extracted_entities.get("medications", [])
                ]
                if len(medications) >= 2:
                    interactions = drug_interaction_service.check_interactions(medications)
                    if interactions:
                        enrichment["drug_interactions"] = interactions
            except Exception as e:
                logger.warning(f"Drug interaction enrichment failed: {e}")

        return enrichment

    async def _detect_language(self, text: str) -> Optional[str]:
        """
        Detect language from user text using MedASR's language detection.

        Falls back to simple heuristics if MedASR is unavailable.
        Returns ISO 639-1 language code (e.g., 'en', 'es', 'fr') or None.
        """
        if not text or len(text.strip()) < 10:
            return None

        try:
            from app.models.medasr_service import get_medasr_service
            import asyncio

            medasr = get_medasr_service()
            if medasr.is_ready() and hasattr(medasr, "detect_language"):
                loop = asyncio.get_event_loop()
                detected = await loop.run_in_executor(
                    None, medasr.detect_language, text
                )
                if detected:
                    return detected[:2]  # Normalize to 2-letter code
        except Exception as e:
            logger.debug(f"MedASR language detection failed: {e}")

        # Simple heuristic fallback based on Unicode ranges
        try:
            # Chinese characters
            if any("\u4e00" <= ch <= "\u9fff" for ch in text):
                return "zh"
            # Arabic script
            if any("\u0600" <= ch <= "\u06ff" for ch in text):
                return "ar"
            # Devanagari (Hindi)
            if any("\u0900" <= ch <= "\u097f" for ch in text):
                return "hi"
            # Common Spanish/French/German/Portuguese indicators
            text_lower = text.lower()
            spanish_markers = ["tengo", "dolor", "estoy", "siento", "hace"]
            french_markers = ["j'ai", "depuis", "douleur", "je suis", "mal"]
            german_markers = ["ich habe", "schmerzen", "seit", "mir ist"]
            portuguese_markers = ["estou", "tenho", "dor", "sinto"]

            for marker in spanish_markers:
                if marker in text_lower:
                    return "es"
            for marker in french_markers:
                if marker in text_lower:
                    return "fr"
            for marker in german_markers:
                if marker in text_lower:
                    return "de"
            for marker in portuguese_markers:
                if marker in text_lower:
                    return "pt"
        except Exception:
            pass

        return None

    @staticmethod
    def _is_end_signal(text: str) -> bool:
        """Check if user wants to end the conversation."""
        end_phrases = [
            "that's all",
            "that's it",
            "nothing else",
            "no more",
            "i'm done",
            "im done",
            "that is all",
            "we're done",
            "finish",
            "end conversation",
            "no, thank you",
            "no thank you",
        ]
        text_lower = text.lower().strip()
        return any(phrase in text_lower for phrase in end_phrases)

    def get_session_data(self) -> Dict[str, Any]:
        """Get serializable session data for persistence with PHI redaction."""
        turns = [t.model_dump(mode="json") for t in self.session.turns]

        # Phase 2: Redact PHI from turns and transcript before persistence
        redacted_turns = redact_conversation_turns(turns)
        redacted_transcript = redact_conversation_transcript(
            self.session.accumulated_transcript
        )

        return {
            "session_id": self.session.session_id,
            "mode": self.session.mode.value,
            "state": self.session.state.value,
            "turns": redacted_turns,
            "accumulated_transcript": redacted_transcript,
            "extracted_entities": self.session.extracted_entities,
            "language": self.session.language,
            "followup_round": self.session.followup_round,
            "created_at": self.session.created_at.isoformat(),
        }
