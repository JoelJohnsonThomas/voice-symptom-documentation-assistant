"""Psychiatry SOAP Template."""

from __future__ import annotations

from app.prompts.specialty._base import SpecialtyTemplate

PSYCHIATRY_TEMPLATE = SpecialtyTemplate(
    name="psychiatry",
    display_name="PSYCHIATRY",
    detection_keywords=[
        r"\banxi(ety|ous)\b",
        r"\bdepress(ed|ion)\b",
        r"\bpanic\b",
        r"\binsomnia\b",
        r"\bcan.?t sleep\b",
        r"\bsuicid\b",
        r"\bself.?harm\b",
        r"\bhallucin\b",
        r"\bvoices?\b",
        r"\bmania\b",
        r"\bbipolar\b",
        r"\bptsd\b",
        r"\btrauma\b",
        r"\bocd\b",
        r"\bcompuls\b",
        r"\bobsess\b",
        r"\bparanoi\b",
        r"\bpsycho(sis|tic)\b",
        r"\beating disorder\b",
        r"\banorexi\b",
        r"\bbulimi\b",
        r"\badhd\b",
        r"\battention deficit\b",
        r"\baddiction\b",
        r"\bsubstance\b",
        r"\bwithdrawal\b",
        r"\boverwhelmed\b",
        r"\bhopeless\b",
        r"\bworthless\b",
        r"\bmood\b",
    ],
    required_subjective_fields=[
        "onset",
        "duration",
        "severity",
        "sleep_pattern",
        "appetite_changes",
        "psychiatric_medications",
        "substance_use",
        "safety_concerns",
    ],
    required_objective_fields=[
        "appearance",
        "behavior",
        "mood_and_affect",
        "thought_process",
        "thought_content",
        "cognition",
        "insight_and_judgment",
        "safety_assessment",
    ],
    objective_prompt=(
        "Document mental status exam: appearance, behavior, mood, affect, thought process, "
        "thought content (including SI/HI screen), cognition, insight, judgment. "
        "Note safety assessment with specific risk and protective factors."
    ),
    assessment_prompt=(
        "Use DSM-5 diagnostic framework. Note symptom duration for diagnostic criteria. "
        "Include functional impairment level (GAF or WHODAS if available). "
        "Document risk level (low/moderate/high) with supporting rationale."
    ),
    plan_prompt=(
        "Include psychotherapy modality, medication management with titration plan, "
        "safety plan if indicated, follow-up frequency, and crisis resources. "
        "Note any coordination with PCP or other providers."
    ),
    additional_sections={
        "Mental Status Exam": (
            "Provide structured MSE: Appearance, Behavior, Speech, Mood (patient-reported), "
            "Affect (observed), Thought Process, Thought Content (SI/HI/delusions), "
            "Perceptions, Cognition, Insight, Judgment."
        ),
        "Risk Assessment": (
            "Document suicide/violence risk level with specific factors: "
            "ideation, intent, plan, means access, protective factors, prior attempts."
        ),
    },
)
