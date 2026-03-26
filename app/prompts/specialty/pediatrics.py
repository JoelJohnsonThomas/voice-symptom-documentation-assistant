"""Pediatrics SOAP Template."""

from __future__ import annotations

from app.prompts.specialty._base import SpecialtyTemplate

PEDIATRICS_TEMPLATE = SpecialtyTemplate(
    name="pediatrics",
    display_name="PEDIATRICS",
    detection_keywords=[
        r"\bchild\b",
        r"\bbaby\b",
        r"\binfant\b",
        r"\btoddler\b",
        r"\bnewborn\b",
        r"\bpediatric\b",
        r"\bmy (son|daughter|kid)\b",
        r"\b(his|her) (son|daughter)\b",
        r"\bmonths?\s?old\b",
        r"\byears?\s?old\b.*\b(child|kid|son|daughter)\b",
        r"\bvaccinat\b",
        r"\bimmuniz\b",
        r"\bgrowth\b",
        r"\bdevelopment(al)?\b",
        r"\bmilestone\b",
        r"\bteething\b",
        r"\bcolic\b",
        r"\bdiaper rash\b",
        r"\bear infection\b",
        r"\bcroup\b",
        r"\brsv\b",
        r"\bhand.?foot.?mouth\b",
    ],
    required_subjective_fields=[
        "age",
        "weight",
        "immunization_status",
        "developmental_milestones",
        "feeding_history",
        "birth_history",
    ],
    required_objective_fields=[
        "vital_signs",
        "weight_percentile",
        "height_percentile",
        "head_circumference_percentile",
        "developmental_assessment",
    ],
    objective_prompt=(
        "Include weight percentile, developmental milestones status, immunization status. "
        "Note age-appropriate vital sign interpretation (use pediatric reference ranges). "
        "Document hydration status and activity level."
    ),
    assessment_prompt=(
        "Consider age-specific differentials. Note parental concern level. "
        "Include growth and development assessment. Flag any developmental delays "
        "or growth chart deviations."
    ),
    plan_prompt=(
        "Include weight-based dosing notes, age-appropriate interventions, "
        "return precautions for caregivers in plain language, pediatric-specific "
        "referral criteria, and anticipatory guidance."
    ),
    additional_sections={
        "Growth Assessment": (
            "Note weight, height, and head circumference percentiles. "
            "Flag any crossing of percentile lines or deviation from growth curve."
        ),
        "Developmental Screening": (
            "Document age-appropriate milestone status: gross motor, fine motor, "
            "language, social-emotional. Note if formal screening tool indicated."
        ),
    },
)
