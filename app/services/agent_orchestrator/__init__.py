"""
Multi-Agent Orchestration Framework (Phase 3)

LangGraph-based agent system with four specialized agents coordinated
by a supervisor:

- **Intake Agent**: Conversation flow, symptom collection, follow-up questions
- **Documentation Agent**: SOAP generation, specialty templates, streaming output
- **Safety Agent**: Emergency detection, PHI scan, prompt injection, output validation
- **Compliance Agent**: FHIR export, ICD-10/CPT coding, drug interactions, audit logging

The supervisor routes incoming events to the appropriate agent(s) based
on the clinical context and conversation state.
"""

from app.services.agent_orchestrator.orchestrator import (
    AgentOrchestrator,
    get_agent_orchestrator,
)
from app.services.agent_orchestrator.state import AgentState, ClinicalContext

__all__ = [
    "AgentOrchestrator",
    "get_agent_orchestrator",
    "AgentState",
    "ClinicalContext",
]
