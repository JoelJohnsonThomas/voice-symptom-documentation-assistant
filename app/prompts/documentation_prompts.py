"""
Compliant Documentation Prompts for MedGemma

COMPLIANCE NOTICE:
These prompts are designed to extract and structure information ONLY.
They explicitly prohibit clinical decision-making, triage, or urgency assessment.
"""

def create_followup_questions_prompt(transcript: str, language: str = "en") -> str:
    """
    Generate clinically grounded follow-up questions for information missing from
    the patient's initial statement.

    Modelled on real triage nurse assessment: demographics, red-flag associated
    symptoms, severity, progression, and relevant history.

    Returns a prompt that asks MedGemma to produce a JSON object with a
    "questions" key containing 2-3 patient-friendly follow-up questions.
    """
    clean_transcript = transcript.replace("</s>", "").replace("<s>", "").strip().lstrip('.')

    language_rule = (
        f"\n- Ask all questions in {language} since that is the patient's language."
        if language != "en"
        else ""
    )

    return f"""A patient has just described their symptoms to a triage nurse. Based ONLY on what the patient said, identify the 2-3 most clinically important pieces of information that are MISSING and would help a clinician assess the case.

Patient Statement: "{clean_transcript}"

Think like an experienced triage nurse. Prioritise missing information in this order:
1. Patient demographics relevant to the complaint — age is almost always important; ask about pregnancy if relevant
2. Objective measurements already available to the patient — e.g. temperature reading if they mention fever, pain score (1-10) if they mention pain
3. "Red flag" associated symptoms specific to the chief complaint:
   - Fever → chills, rash, stiff neck, difficulty breathing, recent travel
   - Chest pain → radiation to arm/jaw/shoulder, sweating, nausea, shortness of breath
   - Headache → sudden "thunderclap" onset, stiff neck, sensitivity to light, vision changes
   - Shortness of breath → chest pain, wheeze, ankle swelling, history of asthma/heart disease
   - Abdominal pain → location, vomiting, diarrhoea, blood in stool, last menstrual period
   - Dizziness/fainting → loss of consciousness, palpitations, positional component
   - Back pain → radiation down the leg, numbness/tingling, bladder or bowel changes
   - Rash → new medications or foods, throat/facial swelling, fever
4. Progression — is it getting better, worse, or staying the same?
5. Relevant history — prior episodes, medications already tried, relevant chronic conditions

Rules:
- Ask ONLY about information the patient has NOT already mentioned
- Each question MUST directly reference the patient's specific symptoms — e.g. if they say "sore throat for two days", ask "Along with the sore throat, have you noticed any fever or swollen glands?" rather than a generic "Do you have any other symptoms?"
- NEVER ask generic health screening questions — every question must be clearly linked to what this patient described
- Use simple, caring, patient-friendly language — no medical jargon
- Each question must be a single clear question
- Generate EXACTLY 2 or 3 questions — never fewer, never more{language_rule}

Respond ONLY with a JSON object in this exact format (no extra text, no markdown):
{{"questions": ["Question 1?", "Question 2?", "Question 3?"]}}"""


def create_documentation_prompt(transcript: str, language: str = "en", followup_qa: list | None = None) -> str:
    """
    Create clean, direct prompt without chat artifacts.
    Cleans transcript before formatting to remove ASR artifacts.
    
    Args:
        transcript: Patient's symptom report
        
    Returns:
        Formatted prompt string
    """
    # Clean the transcript first - remove ASR special tokens
    clean_transcript = transcript.replace("</s>", "").replace("<s>", "").strip().lstrip('.')

    # Build optional follow-up Q&A block
    followup_block = ""
    if followup_qa:
        answered = [qa for qa in followup_qa if qa.get("answer", "").strip()]
        if answered:
            qa_lines = "\n".join(
                f"Q: {qa['question']}\nA: {qa['answer']}" for qa in answered
            )
            followup_block = f"\n\nAdditional information provided by the patient:\n{qa_lines}\n"

    # Direct instruction asking for structured extraction + narrative SOAP
    return f"""Analyze this patient statement for medical documentation.

Patient Statement: "{clean_transcript}"{followup_block}

Extract ONLY information the patient explicitly stated:

1. Main symptoms (comma-separated list, include ALL symptom options if patient is uncertain)
2. Location (body part affected, include any radiation pattern like "back, radiating to leg")
3. Quality/Character (how the symptom feels: sharp, dull, burning, throbbing, aching, pressure, etc.)
4. Duration/timing (when it started or how long, e.g. "2 days", "since Monday", "chronic")
5. Severity (if patient describes intensity: mild, moderate, severe, or numeric scale)
6. Associated symptoms (other symptoms mentioned alongside the main complaint)
7. Brief SOAP Subjective note (1-2 sentences summarizing the history of present illness)

Important extraction rules:
- PRESERVE PATIENT UNCERTAINTY: If patient says "not sure if", "maybe", "or", "could be", include ALL options mentioned
  Example: "Not sure if it is pain or pressure" → Symptoms: "pain or pressure (patient uncertain)"
  Example: "kind of a headache maybe" → Symptoms: "possible headache"
- For radiation patterns (e.g. "radiating to", "spreading to", "goes down to"), include in Location field
- If patient says "back pain radiating to leg", Location should be "back, radiating to leg"
- Include uncertainty language in SOAP note: "Patient reports possible...", "Patient uncertain between..."
- Do not add symptoms or details not stated by patient
- Use "not specified" for fields without explicit information
- Use plain English, no markdown formatting.{chr(10) + f'- BILINGUAL OUTPUT REQUIRED: The patient spoke in {language}. All extracted symptoms and the SOAP subjective note MUST be bilingual, formatted as "[{language} text] / [English translation]".' if language != 'en' else ''}"""


def create_soap_oap_prompt(
    transcript: str,
    subjective_data: dict,
    language: str = "en",
    similar_cases: list | None = None,
) -> str:
    """
    Create a prompt for generating Objective, Assessment, and Plan SOAP sections.
    
    Uses already-extracted Subjective data as context to generate the remaining
    three SOAP sections. These are SUGGESTIONS for clinician review.
    
    Args:
        transcript: Original patient statement
        subjective_data: Dict with chief_complaint, symptom_details, soap_note_subjective
        
    Returns:
        Formatted prompt string for O/A/P generation
    """
    chief_complaint = subjective_data.get("chief_complaint", "not specified")
    soap_subjective = subjective_data.get("soap_note_subjective", "")
    
    symptom_details = subjective_data.get("symptom_details", {})
    symptoms = symptom_details.get("symptoms_mentioned", ["not specified"])
    symptoms_str = ", ".join(symptoms) if isinstance(symptoms, list) else str(symptoms)
    duration = symptom_details.get("duration", "not specified")
    onset = symptom_details.get("onset", "not specified")
    location = symptom_details.get("location", "not specified")
    severity = symptom_details.get("severity_description", "not specified")
    
    # Build optional reference-cases block from RAG retrieval
    # Includes retrieval confidence so the model can weight references appropriately
    reference_block = ""
    if similar_cases:
        case_texts = []
        for i, case in enumerate(similar_cases, start=1):
            doc = case.get("document", "").strip()
            if doc:
                confidence = case.get("retrieval_confidence", "unknown")
                similarity = case.get("similarity", 0)
                section_type = case.get("metadata", {}).get("section_type", "full")
                header = f"Reference case {i} (relevance: {confidence}, similarity: {similarity:.2f}, section: {section_type})"
                case_texts.append(f"{header}:\n{doc}")
        if case_texts:
            reference_block = (
                "\nSimilar past cases (for reference only — do not copy verbatim, "
                "weight higher-relevance cases more heavily):\n"
                + "\n\n".join(case_texts)
                + "\n"
            )

    return f"""You are generating SOAP note sections for CLINICIAN REVIEW.

COMPLIANCE: These are ADMINISTRATIVE SUGGESTIONS only. All clinical decisions
must be made by a qualified healthcare professional. Do NOT make definitive
diagnoses or prescribe specific treatments.
{reference_block}
Patient Information:
- Chief Complaint: {chief_complaint}
- Symptoms: {symptoms_str}
- Duration: {duration}
- Onset: {onset}
- Location: {location}
- Severity: {severity}

Subjective (already documented):
{soap_subjective}

Generate the remaining three SOAP sections. Write each section as a concise,
clinical-style paragraph. Use plain English, no markdown formatting, no bullet
points, no numbered lists.

OBJECTIVE:
Write what a clinician should assess during physical examination. Include
relevant vital signs to check and focused exam findings to look for based
on the presenting symptoms. Use phrases like "recommend assessing" or
"examination should include" since this is a pre-visit suggestion.

ASSESSMENT:
List 2-3 differential diagnoses to consider, ranked by likelihood based on
the symptom presentation. Use cautious language like "consider", "rule out",
"differential includes". Do NOT make a definitive diagnosis.

PLAN:
Suggest reasonable next steps for the clinician to consider. Include relevant
laboratory tests, imaging, or referrals that may be appropriate. Use language
like "consider ordering", "may benefit from", "recommend discussing with patient".
Do NOT prescribe specific medications or dosages.

Format your response exactly as:
OBJECTIVE: [your objective paragraph]
ASSESSMENT: [your assessment paragraph]
PLAN: [your plan paragraph]
{chr(10) + f'BILINGUAL OUTPUT REQUIRED: Since the patient spoke {language}, the generated OBJECTIVE, ASSESSMENT, and PLAN sections MUST be written in both {language} and English (format: "[{language} text] / [English translation]").' if language != 'en' else ''}"""


def create_image_analysis_prompt() -> str:
    """
    Create a prompt for analyzing a medical image.
    
    COMPLIANCE: This produces DESCRIPTIVE observations only.
    It does NOT diagnose conditions or recommend treatments.
    
    Returns:
        Formatted prompt string for image analysis
    """
    return """You are a medical documentation assistant. Describe this clinical image
for administrative documentation purposes.

COMPLIANCE: Provide DESCRIPTIVE OBSERVATIONS ONLY. Do NOT diagnose conditions,
suggest treatments, or make clinical assessments. All findings require clinician review.

Describe the following:
1. Body area visible (e.g., forearm, back, face)
2. Visual observations (color, texture, shape, size, distribution)
3. Any notable features (borders, symmetry, patterns, swelling, discoloration)

Use plain, clinical language. Be factual and objective.
Format your response as:

BODY AREA: [area observed]
OBSERVATIONS: [detailed visual description]
NOTABLE FEATURES: [any distinguishing characteristics]"""


def create_documentation_with_image_prompt(transcript: str, image_description: str, language: str = "en", followup_qa: list | None = None) -> str:
    """
    Create a documentation prompt that includes both transcript and image findings.

    Args:
        transcript: Patient's symptom report
        image_description: AI-generated description of uploaded image
        followup_qa: Optional list of {"question": ..., "answer": ...} dicts

    Returns:
        Formatted prompt string incorporating both text and visual data
    """
    clean_transcript = transcript.replace("</s>", "").replace("<s>", "").strip().lstrip('.')

    # Build optional follow-up Q&A block
    followup_block = ""
    if followup_qa:
        answered = [qa for qa in followup_qa if qa.get("answer", "").strip()]
        if answered:
            qa_lines = "\n".join(
                f"Q: {qa['question']}\nA: {qa['answer']}" for qa in answered
            )
            followup_block = f"\n\nAdditional information provided by the patient:\n{qa_lines}\n"
    
    return f"""Analyze this patient statement AND accompanying image findings for medical documentation.

Patient Statement: "{clean_transcript}"{followup_block}

Image Findings (from uploaded photo):
{image_description}

Extract ONLY information the patient explicitly stated OR that is visible in the image:

1. Main symptoms (comma-separated list, include ALL symptom options if patient is uncertain)
2. Location (body part affected, include any radiation pattern AND image location)
3. Quality/Character (how the symptom feels: sharp, dull, burning, throbbing, aching, pressure, etc.)
4. Duration/timing (when it started or how long, e.g. "2 days", "since Monday", "chronic")
5. Severity (if patient describes intensity: mild, moderate, severe, or numeric scale)
6. Associated symptoms (other symptoms mentioned alongside the main complaint)
7. Visual findings summary (brief summary of what the uploaded image shows)
8. Brief SOAP Subjective note (1-2 sentences summarizing the history of present illness,
   incorporating both verbal report and visual findings)

Important extraction rules:
- PRESERVE PATIENT UNCERTAINTY: If patient says "not sure if", "maybe", "or", "could be", include ALL options mentioned
- For radiation patterns (e.g. "radiating to", "spreading to", "goes down to"), include in Location field
- Include uncertainty language in SOAP note: "Patient reports possible...", "Patient uncertain between..."
- Integrate image findings naturally: "Patient presents with [verbal symptoms]. Uploaded image shows [visual findings]."
- Do not add symptoms or details not stated by patient or visible in the image
- Use "not specified" for fields without explicit information
- Use plain English, no markdown formatting.{chr(10) + f'- BILINGUAL OUTPUT REQUIRED: The patient spoke in {language}. All extracted symptoms and the SOAP subjective note MUST be bilingual, formatted as "[{language} text] / [English translation]".' if language != 'en' else ''}"""
