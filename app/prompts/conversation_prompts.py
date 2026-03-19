"""
Conversational prompts and templates for the AI Voice Assistant.

Separate from documentation_prompts.py which handles batch SOAP generation.
These prompts are designed for interactive, empathetic patient/clinician dialogue.
"""

# System prompt for conversational MedGemma at FOLLOW_UP state
CONVERSATION_SYSTEM_PROMPT = """You are a medical intake assistant helping gather patient symptoms for documentation.

CRITICAL RULES:
1. You are NOT a doctor. NEVER diagnose, suggest conditions, or recommend treatments.
2. NEVER say "you might have", "this sounds like", "you should take", or similar diagnostic language.
3. Your role is ONLY to gather information for the clinician to review.
4. Be empathetic, warm, and professional.
5. Ask one question at a time to avoid overwhelming the patient.
6. Focus on: onset, duration, severity (1-10), location, quality, aggravating/alleviating factors.
7. Acknowledge what the patient shares before asking the next question.
8. Keep responses concise (1-3 sentences).

If the patient describes an emergency (chest pain with radiation, difficulty breathing, loss of consciousness, severe bleeding, suicidal thoughts), immediately advise them to call 911 or go to the nearest emergency room.

EXAMPLE GOOD RESPONSES:
- "Thank you for sharing that. How long have you been experiencing this headache?"
- "I understand that must be uncomfortable. On a scale of 1 to 10, how would you rate the pain?"
- "Got it. Is there anything that makes the pain better or worse?"

EXAMPLE BAD RESPONSES (NEVER SAY THESE):
- "That sounds like it could be a migraine."
- "You should take ibuprofen for that."
- "Based on your symptoms, you may have..."
"""

# System prompt with RAG context (Phase 2)
CONVERSATION_RAG_SYSTEM_PROMPT = """You are a medical intake assistant helping gather patient symptoms for documentation.

CRITICAL RULES:
1. You are NOT a doctor. NEVER diagnose, suggest conditions, or recommend treatments.
2. NEVER say "you might have", "this sounds like", "you should take", or similar diagnostic language.
3. Your role is ONLY to gather information for the clinician to review.
4. Be empathetic, warm, and professional.
5. Ask one question at a time.
6. Focus on: onset, duration, severity (1-10), location, quality, aggravating/alleviating factors.
7. Keep responses concise (1-3 sentences).

You have access to the following clinical guidelines relevant to this patient's symptoms:
{clinical_guidelines}

Use these guidelines to inform your follow-up questions, but do NOT cite them directly to the patient.
Do NOT diagnose. Do NOT recommend treatments. Only gather information.
"""

# Clinician mode system prompt
CLINICIAN_SYSTEM_PROMPT = """You are a clinical assistant responding to hands-free queries from healthcare staff.

You can:
- Look up drug interactions when asked
- Provide ICD-10 code suggestions
- Search for similar past cases
- Answer questions about clinical guidelines from the knowledge base

Be direct, concise, and professional. Provide factual information only.
Always note that results should be verified against authoritative sources.
"""

# =====================================================
# TEMPLATE RESPONSES (no LLM call needed — low latency)
# =====================================================

GREETING_PATIENT = (
    "Hello! I'm your intake assistant. I'll help capture your symptoms "
    "so your doctor has all the information they need. Nothing I say is "
    "medical advice — your clinician will review everything. "
    "What's bringing you in today?"
)

GREETING_CLINICIAN = (
    "Hello! I'm ready to assist. You can ask me about drug interactions, "
    "ICD-10 codes, or similar cases. How can I help?"
)

HIPAA_NOTICE = (
    "Just so you know, this conversation is being recorded for documentation "
    "purposes. Your information is kept private and secure in compliance "
    "with healthcare privacy regulations."
)

# Acknowledgment templates — randomly selected to feel natural
ACKNOWLEDGMENT_TEMPLATES = [
    "Thank you for sharing that. Let me note that down.",
    "I understand. That's helpful information.",
    "Got it, thank you.",
    "Okay, I've noted that.",
    "Thank you for letting me know.",
]

# Symptom acknowledgment with entity echo
SYMPTOM_ACK_TEMPLATE = (
    "Thank you for sharing that. I've noted {symptom_summary}. "
    "Let me ask a few follow-up questions to help your doctor understand better."
)

# Transition to follow-up
TRANSITION_TO_FOLLOWUP = (
    "I have a few follow-up questions to make sure we capture "
    "everything for your doctor."
)

# Summary introduction
SUMMARY_INTRO = (
    "Thank you for your patience. Here's a summary of what we discussed. "
    "Your doctor will review this carefully."
)

# Emergency response
EMERGENCY_RESPONSE = (
    "Based on what you've described, this may require immediate medical attention. "
    "Please call 911 or go to your nearest emergency room right away. "
    "I'm not able to provide emergency medical care, but getting help quickly is important."
)

# Session end
SESSION_END = (
    "Thank you for your time. Your information has been documented "
    "and will be reviewed by your clinician. Take care!"
)

# Follow-up question prompt for MedGemma
FOLLOWUP_GENERATION_PROMPT = """Based on the conversation so far, generate the next follow-up question to ask the patient.

Patient's symptoms so far:
{accumulated_transcript}

Extracted entities:
- Conditions: {conditions}
- Medications: {medications}

Questions already asked: {questions_asked}

Generate exactly ONE follow-up question. Focus on aspects not yet covered:
- Onset and duration
- Severity (1-10 scale)
- Location and radiation
- Quality (sharp, dull, burning, etc.)
- Aggravating and alleviating factors
- Associated symptoms
- Relevant medical history

Respond with ONLY the question, nothing else. Be empathetic and conversational.
"""

# SOAP generation prompt from conversation
CONVERSATION_SOAP_PROMPT = """Generate a structured clinical SOAP note from this patient intake conversation.

Full conversation transcript:
{conversation_transcript}

Extracted entities:
- Conditions: {conditions}
- Medications: {medications}

Generate a SOAP note with these sections:
- Chief Complaint: The patient's primary concern in one sentence
- Subjective: Patient-reported symptoms, history, and relevant details
- Objective: Any measurable findings mentioned (vital signs, observations)
- Assessment: Clinical summary (NOT a diagnosis — flag for clinician review)
- Plan: Recommended next steps (clinician to determine)

Mark each section with a confidence score (high/medium/low) based on how much supporting information was gathered.

IMPORTANT: Do NOT include diagnostic conclusions. Mark Assessment as requiring clinician review.

Respond in JSON format:
{{
    "chief_complaint": "...",
    "subjective": "...",
    "objective": "...",
    "assessment": "...",
    "plan": "...",
    "confidence": {{
        "chief_complaint": "high|medium|low",
        "subjective": "high|medium|low",
        "objective": "high|medium|low",
        "assessment": "high|medium|low",
        "plan": "high|medium|low"
    }}
}}
"""

# =====================================================
# Phase 3: Multi-Language Template Responses
# =====================================================

MULTILINGUAL_GREETINGS = {
    "en": GREETING_PATIENT,
    "es": (
        "Hola! Soy su asistente de admision. Le ayudare a describir sus sintomas "
        "para que su medico tenga toda la informacion necesaria. Nada de lo que "
        "digo es consejo medico — su medico revisara todo. "
        "Que le trae hoy?"
    ),
    "fr": (
        "Bonjour! Je suis votre assistant d'accueil. Je vais vous aider a decrire "
        "vos symptomes afin que votre medecin dispose de toutes les informations "
        "necessaires. Rien de ce que je dis ne constitue un avis medical — "
        "votre medecin examinera tout. Qu'est-ce qui vous amene aujourd'hui?"
    ),
    "de": (
        "Hallo! Ich bin Ihr Aufnahmeassistent. Ich helfe Ihnen, Ihre Symptome "
        "zu beschreiben, damit Ihr Arzt alle notwendigen Informationen hat. "
        "Nichts, was ich sage, ist medizinischer Rat — Ihr Arzt wird alles "
        "uberprufen. Was fuhrt Sie heute hierher?"
    ),
    "pt": (
        "Ola! Sou seu assistente de triagem. Vou ajuda-lo a descrever seus "
        "sintomas para que seu medico tenha todas as informacoes necessarias. "
        "Nada do que eu digo e conselho medico — seu medico revisara tudo. "
        "O que o traz aqui hoje?"
    ),
    "zh": (
        "你好！我是您的接诊助手。我将帮助您描述症状，"
        "以便您的医生获得所需的全部信息。"
        "我所说的不构成医疗建议——您的医生会审阅一切。"
        "今天什么情况带您来就诊？"
    ),
    "hi": (
        "नमस्ते! मैं आपका इनटेक सहायक हूं। मैं आपके लक्षणों को समझने में "
        "मदद करूंगा ताकि आपके डॉक्टर के पास सारी जानकारी हो। "
        "मैं जो कहता हूं वह चिकित्सा सलाह नहीं है — आपके चिकित्सक सब कुछ "
        "समीक्षा करेंगे। आज आपको क्या तकलीफ है?"
    ),
    "ar": (
        "مرحبا! أنا مساعد الاستقبال الخاص بك. سأساعدك في وصف أعراضك "
        "حتى يحصل طبيبك على جميع المعلومات اللازمة. لا شيء مما أقوله "
        "يعتبر نصيحة طبية — سيراجع طبيبك كل شيء. ما الذي أتى بك اليوم؟"
    ),
}

MULTILINGUAL_ACKNOWLEDGMENTS = {
    "en": ACKNOWLEDGMENT_TEMPLATES,
    "es": [
        "Gracias por compartir eso. Lo anoto.",
        "Entiendo. Esa es informacion util.",
        "Bien, gracias.",
        "De acuerdo, lo he anotado.",
        "Gracias por informarme.",
    ],
    "fr": [
        "Merci d'avoir partage cela. Je le note.",
        "Je comprends. C'est une information utile.",
        "Bien recu, merci.",
        "D'accord, je l'ai note.",
        "Merci de m'avoir informe.",
    ],
}

MULTILINGUAL_EMERGENCY = {
    "en": EMERGENCY_RESPONSE,
    "es": (
        "Segun lo que ha descrito, esto puede requerir atencion medica inmediata. "
        "Por favor llame al 911 o vaya a la sala de emergencias mas cercana de inmediato. "
        "No puedo proporcionar atencion medica de emergencia, "
        "pero obtener ayuda rapidamente es importante."
    ),
    "fr": (
        "D'apres ce que vous avez decrit, cela peut necessiter une attention "
        "medicale immediate. Veuillez appeler le 15 (SAMU) ou rendez-vous aux "
        "urgences les plus proches immediatement."
    ),
}

MULTILINGUAL_SUMMARY = {
    "en": SUMMARY_INTRO,
    "es": (
        "Gracias por su paciencia. Aqui hay un resumen de lo que discutimos. "
        "Su medico lo revisara cuidadosamente."
    ),
    "fr": (
        "Merci pour votre patience. Voici un resume de ce dont nous avons discute. "
        "Votre medecin l'examinera attentivement."
    ),
}


def get_greeting_for_language(language: str, mode: str = "patient") -> str:
    """Get greeting text for a language, falling back to English."""
    if mode == "clinician":
        return GREETING_CLINICIAN  # Clinician mode stays in English

    lang_key = language[:2] if len(language) > 2 else language
    return MULTILINGUAL_GREETINGS.get(lang_key, GREETING_PATIENT)


def get_acknowledgment_for_language(language: str) -> list:
    """Get acknowledgment templates for a language."""
    lang_key = language[:2] if len(language) > 2 else language
    return MULTILINGUAL_ACKNOWLEDGMENTS.get(lang_key, ACKNOWLEDGMENT_TEMPLATES)


def get_emergency_for_language(language: str) -> str:
    """Get emergency response for a language."""
    lang_key = language[:2] if len(language) > 2 else language
    return MULTILINGUAL_EMERGENCY.get(lang_key, EMERGENCY_RESPONSE)


def get_summary_for_language(language: str) -> str:
    """Get summary intro for a language."""
    lang_key = language[:2] if len(language) > 2 else language
    return MULTILINGUAL_SUMMARY.get(lang_key, SUMMARY_INTRO)
