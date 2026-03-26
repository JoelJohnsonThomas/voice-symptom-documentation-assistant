"""Primary Care SOAP Template."""

from __future__ import annotations

from app.prompts.specialty._base import SpecialtyTemplate

PRIMARY_CARE_TEMPLATE = SpecialtyTemplate(
    name="primary_care",
    display_name="PRIMARY CARE",
    detection_keywords=[
        r"\bcheck.?up\b",
        r"\bannual\b",
        r"\bphysical\b",
        r"\bpreventive\b",
        r"\bscreening\b",
        r"\bfollow.?up\b",
        r"\brefill\b",
        r"\bchronic\b",
        r"\bdiabetes\b",
        r"\bhypertension\b",
        r"\bhigh blood pressure\b",
        r"\bcholesterol\b",
        r"\bcold\b",
        r"\bflu\b",
        r"\bcough\b",
        r"\bsore throat\b",
        r"\bear\s?(ache|infection|pain)\b",
        r"\bsinus\b",
        r"\ballerg(y|ies)\b",
        r"\bfatigue\b",
        r"\bweight\b",
        r"\bsleep\b",
    ],
    required_subjective_fields=[
        "duration",
        "severity",
        "medications",
        "medical_history",
        "allergies",
    ],
    required_objective_fields=[
        "vital_signs",
        "bmi",
        "relevant_exam_findings",
    ],
    objective_prompt=(
        "Include preventive screening status, BMI, relevant chronic disease markers "
        "(HbA1c, lipid panel dates), and immunization status if relevant. "
        "Note medication adherence observations."
    ),
    assessment_prompt=(
        "Consider chronic disease progression alongside acute presentation. "
        "Note medication adherence concerns. Include preventive care gaps identified."
    ),
    plan_prompt=(
        "Include follow-up interval, medication adjustments, lifestyle modifications, "
        "preventive care due, and referral indications. Note patient education provided."
    ),
)
