"""Base dataclass for specialty templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SpecialtyTemplate:
    """A specialty-specific SOAP template with required fields and prompts."""

    name: str
    display_name: str
    required_subjective_fields: List[str] = field(default_factory=list)
    required_objective_fields: List[str] = field(default_factory=list)
    objective_prompt: str = ""
    assessment_prompt: str = ""
    plan_prompt: str = ""
    additional_sections: Dict[str, str] = field(default_factory=dict)
    detection_keywords: List[str] = field(default_factory=list)
