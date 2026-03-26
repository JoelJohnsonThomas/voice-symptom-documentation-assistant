"""
Shared state for the multi-agent orchestration system.

Uses a typed dict as the LangGraph state schema so all agents
read/write the same structure.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    SUPERVISOR = "supervisor"
    INTAKE = "intake"
    DOCUMENTATION = "documentation"
    SAFETY = "safety"
    COMPLIANCE = "compliance"


class ClinicalContext(BaseModel):
    """Accumulated clinical context from the conversation."""

    chief_complaint: str = ""
    symptoms: List[str] = Field(default_factory=list)
    entities: Dict[str, Any] = Field(default_factory=dict)
    vitals: Dict[str, Any] = Field(default_factory=dict)
    transcript: str = ""
    diarized_segments: List[Dict[str, Any]] = Field(default_factory=list)
    detected_language: str = "en"
    detected_specialty: str = "general"
    patient_age: Optional[int] = None
    followup_qa: List[Dict[str, str]] = Field(default_factory=list)
    rag_context: List[Dict[str, Any]] = Field(default_factory=list)
    clinical_guidelines: List[Dict[str, Any]] = Field(default_factory=list)
    drug_interactions: List[Dict[str, Any]] = Field(default_factory=list)
    icd10_suggestions: List[Dict[str, Any]] = Field(default_factory=list)


class SafetyStatus(BaseModel):
    """Safety evaluation from the Safety Agent."""

    is_emergency: bool = False
    emergency_type: Optional[str] = None
    red_flags: List[str] = Field(default_factory=list)
    phi_detected: bool = False
    phi_locations: List[Dict[str, Any]] = Field(default_factory=list)
    prompt_injection_detected: bool = False
    injection_details: Optional[str] = None
    risk_level: str = "low"  # low, medium, high, critical


class DocumentationResult(BaseModel):
    """Generated documentation from the Documentation Agent."""

    soap_subjective: str = ""
    soap_objective: str = ""
    soap_assessment: str = ""
    soap_plan: str = ""
    confidence: Dict[str, Any] = Field(default_factory=dict)
    hallucination_check: Dict[str, Any] = Field(default_factory=dict)
    specialty_template_used: str = "general"


class ComplianceResult(BaseModel):
    """Compliance outputs from the Compliance Agent."""

    fhir_bundle: Optional[Dict[str, Any]] = None
    icd10_codes: List[Dict[str, Any]] = Field(default_factory=list)
    cpt_codes: List[Dict[str, Any]] = Field(default_factory=list)
    audit_logged: bool = False
    phi_redacted_transcript: str = ""


class AgentMessage(BaseModel):
    """Message passed between agents."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: AgentRole
    to_agent: AgentRole
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentState(BaseModel):
    """
    Top-level state shared across all agents in the orchestration graph.

    This is the LangGraph state schema — each node reads and writes
    specific fields.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_mode: str = "patient"  # patient, clinician, ambient
    turn_count: int = 0

    # Input for current turn
    current_input: str = ""
    current_audio_segment: Optional[bytes] = None

    # Clinical context (accumulated across turns)
    clinical_context: ClinicalContext = Field(default_factory=ClinicalContext)

    # Agent outputs
    safety_status: SafetyStatus = Field(default_factory=SafetyStatus)
    documentation: DocumentationResult = Field(default_factory=DocumentationResult)
    compliance: ComplianceResult = Field(default_factory=ComplianceResult)

    # Supervisor routing
    next_agents: List[AgentRole] = Field(default_factory=list)
    completed_agents: List[AgentRole] = Field(default_factory=list)

    # Response to user
    response_text: str = ""
    response_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Message bus between agents
    messages: List[AgentMessage] = Field(default_factory=list)

    # Flags
    is_final: bool = False
    needs_followup: bool = False
    ready_for_documentation: bool = False
