"""Emergency Medicine SOAP Template."""

from __future__ import annotations

from app.prompts.specialty._base import SpecialtyTemplate

EMERGENCY_TEMPLATE = SpecialtyTemplate(
    name="emergency",
    display_name="EMERGENCY MEDICINE",
    detection_keywords=[
        r"\bchest pain\b",
        r"\bshortness of breath\b",
        r"\bdifficulty breathing\b",
        r"\btrauma\b",
        r"\bfall\b",
        r"\baccident\b",
        r"\bseizure\b",
        r"\bunconscious\b",
        r"\bfainted\b",
        r"\bbleeding\b",
        r"\boverdose\b",
        r"\banaphyla\b",
        r"\bstroke\b",
        r"\bslurred speech\b",
        r"\bweakness on one side\b",
        r"\bsevere pain\b",
        r"\bfracture\b",
        r"\bbroken\b",
        r"\bburns?\b",
        r"\bstabbing\b",
        r"\bgunshot\b",
        r"\bsuicid\b",
        r"\bcardiac arrest\b",
        r"\bheart attack\b",
    ],
    required_subjective_fields=[
        "mechanism_of_injury",
        "onset_time",
        "severity_score",
        "allergies",
        "current_medications",
        "last_oral_intake",
    ],
    required_objective_fields=[
        "vital_signs",
        "airway_status",
        "breathing_assessment",
        "circulation_assessment",
        "gcs_score",
        "pain_scale",
    ],
    objective_prompt=(
        "Focus on ABCs (Airway, Breathing, Circulation), GCS score, trauma survey "
        "findings, point-of-care labs (troponin, lactate, blood gas), and ECG interpretation. "
        "Note hemodynamic stability. Include ESI triage level recommendation."
    ),
    assessment_prompt=(
        "Prioritize life-threatening differentials first. Use ESI-level language. "
        "Include disposition recommendation (admit, observe, discharge). "
        "Flag any time-sensitive conditions (STEMI, stroke, sepsis)."
    ),
    plan_prompt=(
        "Include resuscitation steps if indicated, IV access, monitoring orders, "
        "consult recommendations, reassessment timeline, and disposition plan. "
        "Note any critical decision points (e.g., cath lab activation criteria)."
    ),
    additional_sections={
        "ESI Level": (
            "Assign Emergency Severity Index level 1-5 based on presentation: "
            "1=immediate life-saving, 2=high risk, 3=many resources, "
            "4=one resource, 5=no resources needed."
        ),
    },
)
