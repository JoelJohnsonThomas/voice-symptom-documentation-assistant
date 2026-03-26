"""
Specialty-Specific SOAP Templates (Phase 2)

Auto-detects clinical specialty from chief complaint and provides
specialty-appropriate prompt context, required fields, and documentation
structure for SOAP note generation.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.prompts.specialty._base import SpecialtyTemplate
from app.prompts.specialty.emergency import EMERGENCY_TEMPLATE
from app.prompts.specialty.primary_care import PRIMARY_CARE_TEMPLATE
from app.prompts.specialty.psychiatry import PSYCHIATRY_TEMPLATE
from app.prompts.specialty.ob_gyn import OB_GYN_TEMPLATE
from app.prompts.specialty.pediatrics import PEDIATRICS_TEMPLATE


# Registry of all specialty templates
SPECIALTY_REGISTRY: Dict[str, SpecialtyTemplate] = {
    "emergency": EMERGENCY_TEMPLATE,
    "primary_care": PRIMARY_CARE_TEMPLATE,
    "psychiatry": PSYCHIATRY_TEMPLATE,
    "ob_gyn": OB_GYN_TEMPLATE,
    "pediatrics": PEDIATRICS_TEMPLATE,
}


def detect_specialty(chief_complaint: str, patient_age: Optional[int] = None) -> str:
    """Auto-detect the most likely clinical specialty from chief complaint.

    Args:
        chief_complaint: The patient's chief complaint text.
        patient_age: Patient age in years (if known).

    Returns:
        Specialty key (e.g. "emergency", "primary_care") or "general".
    """
    text = chief_complaint.lower().strip()

    # Pediatrics: age-based override
    if patient_age is not None and patient_age < 18:
        return "pediatrics"

    # Score each specialty by keyword matches
    best_specialty = "general"
    best_score = 0

    for name, template in SPECIALTY_REGISTRY.items():
        score = sum(1 for kw in template.detection_keywords if re.search(kw, text))
        if score > best_score:
            best_score = score
            best_specialty = name

    return best_specialty if best_score > 0 else "general"


def get_specialty_template(specialty: str) -> Optional[SpecialtyTemplate]:
    """Get the template for a given specialty."""
    return SPECIALTY_REGISTRY.get(specialty)


def build_specialty_prompt_context(specialty: str) -> str:
    """Build the full specialty-specific prompt addition for SOAP generation.

    Returns an empty string for "general" or unknown specialties.
    """
    template = SPECIALTY_REGISTRY.get(specialty)
    if not template:
        return ""

    lines = [f"\nSPECIALTY CONTEXT ({template.display_name}):"]

    if template.required_subjective_fields:
        lines.append(
            "Required subjective information: "
            + ", ".join(template.required_subjective_fields)
        )

    if template.required_objective_fields:
        lines.append(
            "Required objective elements: "
            + ", ".join(template.required_objective_fields)
        )

    lines.append(f"- Objective focus: {template.objective_prompt}")
    lines.append(f"- Assessment focus: {template.assessment_prompt}")
    lines.append(f"- Plan focus: {template.plan_prompt}")

    for section_name, section_prompt in template.additional_sections.items():
        lines.append(f"- {section_name}: {section_prompt}")

    return "\n".join(lines) + "\n"


def get_missing_fields(
    specialty: str,
    subjective_data: dict,
) -> List[str]:
    """Identify specialty-required fields missing from the subjective data.

    Useful for generating targeted follow-up questions.
    """
    template = SPECIALTY_REGISTRY.get(specialty)
    if not template:
        return []

    missing = []
    symptom_details = subjective_data.get("symptom_details", {})
    all_data = {**subjective_data, **symptom_details}

    for req_field in template.required_subjective_fields:
        key = req_field.lower().replace(" ", "_")
        value = all_data.get(key, "")
        if not value or value == "not specified":
            missing.append(req_field)

    return missing
