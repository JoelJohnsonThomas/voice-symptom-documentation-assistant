"""
Unit tests for AI Voice Assistant dialogue manager and safety guardrails.

Tests cover:
- Dialogue state machine transitions
- Emergency detection and escalation
- Non-diagnostic language enforcement
- Treatment safety filtering
- Red flag symptom detection
- PHI redaction for conversation data
- Clinician intent classification
- End-of-conversation signal detection
"""

import pytest

from app.models.conversation_session import (
    ConversationMode,
    ConversationSessionData,
    ConversationState,
)
from app.models.safety_guardrails import (
    check_emergency,
    check_red_flags,
    enforce_non_diagnostic,
    enforce_treatment_safety,
    full_safety_filter,
    redact_conversation_transcript,
    redact_conversation_turns,
)
from app.models.dialogue_manager import DialogueManager


# =====================================================
# Emergency Detection Tests
# =====================================================

class TestEmergencyDetection:
    def test_chest_pain_radiating(self):
        is_emerg, matched = check_emergency("I have chest pain radiating to my left arm")
        assert is_emerg is True
        assert matched is not None

    def test_cant_breathe(self):
        is_emerg, _ = check_emergency("I can't breathe properly")
        assert is_emerg is True

    def test_suicidal(self):
        is_emerg, _ = check_emergency("I've been having suicidal thoughts")
        assert is_emerg is True

    def test_kill_myself(self):
        is_emerg, _ = check_emergency("I want to kill myself")
        assert is_emerg is True

    def test_overdose(self):
        is_emerg, _ = check_emergency("I think I overdosed on my medication")
        assert is_emerg is True

    def test_severe_bleeding(self):
        is_emerg, _ = check_emergency("I have severe bleeding that won't stop")
        assert is_emerg is True

    def test_anaphylaxis(self):
        is_emerg, _ = check_emergency("I think I'm having anaphylaxis")
        assert is_emerg is True

    def test_normal_symptom_not_emergency(self):
        is_emerg, _ = check_emergency("I have a headache and mild fever")
        assert is_emerg is False

    def test_sore_throat_not_emergency(self):
        is_emerg, _ = check_emergency("My throat is sore for two days")
        assert is_emerg is False

    def test_empty_text(self):
        is_emerg, _ = check_emergency("")
        assert is_emerg is False

    def test_stroke_symptoms(self):
        is_emerg, _ = check_emergency("I think I'm having a stroke, my face is drooping")
        assert is_emerg is True

    def test_seizure_now(self):
        is_emerg, _ = check_emergency("My child is having a seizure right now")
        assert is_emerg is True


# =====================================================
# Non-Diagnostic Language Enforcement Tests
# =====================================================

class TestNonDiagnosticEnforcement:
    def test_you_have(self):
        result = enforce_non_diagnostic("Based on what you told me, you have a migraine")
        assert "you have" not in result.lower()
        assert "doctor will evaluate" in result.lower()

    def test_sounds_like(self):
        result = enforce_non_diagnostic("This sounds like strep throat")
        assert "sounds like" not in result.lower()

    def test_you_should_take(self):
        result = enforce_non_diagnostic("You should take ibuprofen for the pain")
        assert "you should take" not in result.lower()
        assert "doctor may recommend" in result.lower()

    def test_diagnosis(self):
        result = enforce_non_diagnostic("My diagnosis is bronchitis")
        assert "diagnosis" not in result.lower()

    def test_safe_text_unchanged(self):
        safe_text = "Thank you for sharing that. How long have you had this headache?"
        result = enforce_non_diagnostic(safe_text)
        assert result == safe_text

    def test_prescription(self):
        result = enforce_non_diagnostic("I'll prescribe you some antibiotics")
        assert "prescri" not in result.lower()


# =====================================================
# Treatment Safety Filter Tests (Phase 2)
# =====================================================

class TestTreatmentSafety:
    def test_dosage_recommendation(self):
        result = enforce_treatment_safety("Take 500mg of acetaminophen")
        assert "500mg" not in result
        assert "doctor will advise" in result.lower()

    def test_recommend_taking(self):
        result = enforce_treatment_safety("I recommend taking aspirin daily")
        assert "recommend taking" not in result.lower()

    def test_stop_taking(self):
        result = enforce_treatment_safety("You should stop taking that medication")
        assert "consult your doctor" in result.lower()

    def test_surgery_needed(self):
        result = enforce_treatment_safety("You need a surgery to fix this")
        assert "doctor will determine" in result.lower()


# =====================================================
# Full Safety Filter Tests (Phase 2)
# =====================================================

class TestFullSafetyFilter:
    def test_combines_both_filters(self):
        text = "You have a migraine. Take 400mg of ibuprofen."
        result = full_safety_filter(text)
        assert "you have" not in result.lower()
        assert "400mg" not in result


# =====================================================
# Red Flag Detection Tests
# =====================================================

class TestRedFlagDetection:
    def test_chest_pain_flag(self):
        flags = check_red_flags("Patient reports chest pain for 3 days")
        assert "chest pain" in flags

    def test_multiple_flags(self):
        flags = check_red_flags(
            "Patient has chest pain and shortness of breath with unexplained weight loss"
        )
        assert "chest pain" in flags
        assert "shortness of breath" in flags
        assert "unexplained weight loss" in flags

    def test_no_flags(self):
        flags = check_red_flags("Mild headache and runny nose for 2 days")
        assert len(flags) == 0

    def test_blood_in_stool(self):
        flags = check_red_flags("Noticed blood in stool this morning")
        assert "blood in stool" in flags

    def test_hemoptysis(self):
        flags = check_red_flags("Patient reports hemoptysis")
        assert "hemoptysis" in flags


# =====================================================
# PHI Redaction Tests (Phase 2)
# =====================================================

class TestPHIRedaction:
    def test_redact_phone(self):
        result = redact_conversation_transcript("Call me at 555-123-4567")
        assert "555-123-4567" not in result
        assert "REDACTED" in result

    def test_redact_email(self):
        result = redact_conversation_transcript("Email me at patient@example.com")
        assert "patient@example.com" not in result
        assert "REDACTED" in result

    def test_redact_ssn(self):
        result = redact_conversation_transcript("My SSN is 123-45-6789")
        assert "123-45-6789" not in result
        assert "REDACTED" in result

    def test_medical_content_preserved(self):
        result = redact_conversation_transcript(
            "I have a headache and fever for 3 days"
        )
        assert "headache" in result
        assert "fever" in result

    def test_redact_turns(self):
        turns = [
            {"role": "user", "content": "My SSN is 123-45-6789"},
            {"role": "assistant", "content": "Thank you for sharing."},
        ]
        redacted = redact_conversation_turns(turns)
        assert "123-45-6789" not in redacted[0]["content"]
        assert "Thank you" in redacted[1]["content"]

    def test_empty_transcript(self):
        result = redact_conversation_transcript("")
        assert result == ""

    def test_none_transcript(self):
        result = redact_conversation_transcript(None)
        assert result == ""


# =====================================================
# Clinician Intent Classification Tests (Phase 2)
# =====================================================

class TestClinicianIntentClassification:
    def test_drug_interaction_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "check drug interaction between metformin and lisinopril"
        ) == "drug_interaction"

    def test_safe_to_combine(self):
        assert DialogueManager._classify_clinician_intent(
            "is it safe to combine aspirin and warfarin"
        ) == "drug_interaction"

    def test_icd10_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "icd-10 code for persistent cough"
        ) == "icd10"

    def test_billing_code_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "what's the billing code for type 2 diabetes"
        ) == "icd10"

    def test_similar_case_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "find similar cases to chest pain with shortness of breath"
        ) == "similar_cases"

    def test_guideline_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "what are the guidelines for hypertension management"
        ) == "guidelines"

    def test_protocol_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "what's the protocol for sepsis screening"
        ) == "guidelines"

    def test_unknown_intent(self):
        assert DialogueManager._classify_clinician_intent(
            "hello how are you"
        ) == "unknown"


# =====================================================
# End Signal Detection Tests
# =====================================================

class TestEndSignalDetection:
    def test_thats_all(self):
        assert DialogueManager._is_end_signal("that's all") is True

    def test_im_done(self):
        assert DialogueManager._is_end_signal("I'm done") is True

    def test_nothing_else(self):
        assert DialogueManager._is_end_signal("nothing else to add") is True

    def test_not_end_signal(self):
        assert DialogueManager._is_end_signal("I also have back pain") is False

    def test_no_thank_you(self):
        assert DialogueManager._is_end_signal("no, thank you") is True

    def test_regular_answer(self):
        assert DialogueManager._is_end_signal("About 3 days ago") is False


# =====================================================
# Conversation Session Data Tests
# =====================================================

class TestConversationSessionData:
    def test_initial_state(self):
        session = ConversationSessionData()
        assert session.state == ConversationState.GREETING
        assert session.mode == ConversationMode.PATIENT
        assert len(session.turns) == 0
        assert session.accumulated_transcript == ""

    def test_add_turn(self):
        session = ConversationSessionData()
        session.add_turn("user", "I have a headache")
        assert len(session.turns) == 1
        assert session.turns[0].role == "user"
        assert session.turns[0].content == "I have a headache"
        assert session.accumulated_transcript == "I have a headache"

    def test_accumulate_transcript(self):
        session = ConversationSessionData()
        session.add_turn("user", "I have a headache")
        session.add_turn("user", "for 3 days")
        assert session.accumulated_transcript == "I have a headache for 3 days"

    def test_assistant_turn_not_in_transcript(self):
        session = ConversationSessionData()
        session.add_turn("user", "I have a headache")
        session.add_turn("assistant", "How long have you had it?")
        assert "How long" not in session.accumulated_transcript

    def test_conversation_history(self):
        session = ConversationSessionData()
        session.add_turn("user", "Hello")
        session.add_turn("assistant", "Hi there")
        history = session.get_conversation_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there"}

    def test_clinician_mode(self):
        session = ConversationSessionData(mode=ConversationMode.CLINICIAN)
        assert session.mode == ConversationMode.CLINICIAN


# =====================================================
# Dialogue Manager Initialization Tests
# =====================================================

class TestDialogueManagerInit:
    def test_patient_mode(self):
        dm = DialogueManager(mode=ConversationMode.PATIENT)
        assert dm.session.mode == ConversationMode.PATIENT

    def test_clinician_mode(self):
        dm = DialogueManager(mode=ConversationMode.CLINICIAN)
        assert dm.session.mode == ConversationMode.CLINICIAN

    def test_custom_language(self):
        dm = DialogueManager(language="es")
        assert dm.session.language == "es"

    def test_session_id_generated(self):
        dm = DialogueManager()
        assert dm.session.session_id is not None
        assert len(dm.session.session_id) > 0
