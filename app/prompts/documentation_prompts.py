"""
Compliant Documentation Prompts for MedGemma

COMPLIANCE NOTICE:
These prompts are designed to extract and structure information ONLY.
They explicitly prohibit clinical decision-making, triage, or urgency assessment.
"""

def create_documentation_prompt(transcript: str) -> str:
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
    
    # Direct instruction asking for structured extraction + narrative SOAP
    return f"""Analyze this patient statement for medical documentation.

Patient Statement: "{clean_transcript}"

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
- Use plain English, no markdown formatting."""


def create_soap_oap_prompt(transcript: str, subjective_data: dict) -> str:
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
    
    return f"""You are generating SOAP note sections for CLINICIAN REVIEW.

COMPLIANCE: These are ADMINISTRATIVE SUGGESTIONS only. All clinical decisions
must be made by a qualified healthcare professional. Do NOT make definitive
diagnoses or prescribe specific treatments.

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
PLAN: [your plan paragraph]"""


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


def create_documentation_with_image_prompt(transcript: str, image_description: str) -> str:
    """
    Create a documentation prompt that includes both transcript and image findings.
    
    Args:
        transcript: Patient's symptom report
        image_description: AI-generated description of uploaded image
        
    Returns:
        Formatted prompt string incorporating both text and visual data
    """
    clean_transcript = transcript.replace("</s>", "").replace("<s>", "").strip().lstrip('.')
    
    return f"""Analyze this patient statement AND accompanying image findings for medical documentation.

Patient Statement: "{clean_transcript}"

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
- Use plain English, no markdown formatting."""
