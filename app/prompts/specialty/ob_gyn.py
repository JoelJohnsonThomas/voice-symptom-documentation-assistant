"""OB/GYN SOAP Template."""

from __future__ import annotations

from app.prompts.specialty._base import SpecialtyTemplate

OB_GYN_TEMPLATE = SpecialtyTemplate(
    name="ob_gyn",
    display_name="OB/GYN",
    detection_keywords=[
        r"\bpregnant\b",
        r"\bpregnancy\b",
        r"\bperiod\b",
        r"\bmenstrua\b",
        r"\bbleeding\b.*\b(vaginal|period|menstrual)\b",
        r"\bvaginal\b",
        r"\bpelvic\b",
        r"\bcontracept\b",
        r"\bbirth control\b",
        r"\bprenatal\b",
        r"\bpostnatal\b",
        r"\bpostpartum\b",
        r"\bmiscarriage\b",
        r"\bfertility\b",
        r"\bovarian\b",
        r"\buterine\b",
        r"\bcervical\b",
        r"\bpap smear\b",
        r"\bbreast\s?(lump|pain|mass)\b",
        r"\bcramp(s|ing)\b",
        r"\bmorning sickness\b",
        r"\bnausea\b.*\bpregnant\b",
        r"\blmp\b",
        r"\blast menstrual period\b",
        r"\bgestational\b",
    ],
    required_subjective_fields=[
        "lmp",
        "gravida_para",
        "gestational_age",
        "pregnancy_status",
        "contraception_method",
        "obstetric_history",
    ],
    required_objective_fields=[
        "vital_signs",
        "fundal_height",
        "fetal_heart_tones",
        "cervical_exam",
        "pelvic_exam_findings",
    ],
    objective_prompt=(
        "Include LMP, gravida/para status if relevant, gestational age if pregnant. "
        "Note cervical exam findings, fetal heart tones, fundal height as applicable. "
        "Document any vaginal bleeding characteristics (amount, color, clots)."
    ),
    assessment_prompt=(
        "Consider obstetric vs gynecologic etiologies. Note pregnancy-specific "
        "differential diagnoses and risk factors. Include pregnancy viability assessment "
        "if applicable."
    ),
    plan_prompt=(
        "Include pregnancy-safe medication considerations, prenatal/postnatal care plan, "
        "imaging appropriate for pregnancy status (avoid ionizing radiation if pregnant), "
        "OB consultation thresholds, and follow-up timeline."
    ),
    additional_sections={
        "Obstetric Status": (
            "If pregnant: document G_P_ status, gestational age, EDD, "
            "fetal movement, complications, and prenatal lab status."
        ),
    },
)
