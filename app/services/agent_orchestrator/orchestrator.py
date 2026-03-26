"""
Agent Orchestrator — Supervisor that coordinates the 4 specialized agents.

Implements a LangGraph-compatible state machine that routes events to
agents based on conversation state and clinical context. Falls back to
a simple sequential execution if LangGraph is not installed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.agent_orchestrator.state import (
    AgentRole,
    AgentState,
    ClinicalContext,
)
from app.services.agent_orchestrator.agents.intake_agent import IntakeAgent
from app.services.agent_orchestrator.agents.documentation_agent import DocumentationAgent
from app.services.agent_orchestrator.agents.safety_agent import SafetyAgent
from app.services.agent_orchestrator.agents.compliance_agent import ComplianceAgent

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Supervisor that coordinates the 4 specialized agents.

    Execution flow per turn:
    1. Safety + Intake run in parallel (safety can abort the pipeline)
    2. If ready_for_documentation: Documentation Agent runs
    3. If documentation complete: Compliance Agent runs
    4. Safety validates final output

    Falls back to sequential execution if LangGraph is not available.
    """

    def __init__(self):
        self.intake = IntakeAgent()
        self.documentation = DocumentationAgent()
        self.safety = SafetyAgent()
        self.compliance = ComplianceAgent()
        self._graph = None
        self._build_graph()

    def _build_graph(self) -> None:
        """Build LangGraph state graph if available."""
        try:
            from langgraph.graph import StateGraph, END

            builder = StateGraph(AgentState)

            # Add nodes
            builder.add_node("safety", self._run_safety)
            builder.add_node("intake", self._run_intake)
            builder.add_node("documentation", self._run_documentation)
            builder.add_node("compliance", self._run_compliance)
            builder.add_node("output_validation", self._run_output_validation)

            # Entry: always start with safety
            builder.set_entry_point("safety")

            # Safety -> Intake (unless emergency)
            builder.add_conditional_edges(
                "safety",
                self._after_safety,
                {
                    "intake": "intake",
                    "end": END,
                },
            )

            # Intake -> Documentation or END
            builder.add_conditional_edges(
                "intake",
                self._after_intake,
                {
                    "documentation": "documentation",
                    "end": END,
                },
            )

            # Documentation -> Compliance
            builder.add_edge("documentation", "compliance")

            # Compliance -> Output Validation
            builder.add_edge("compliance", "output_validation")

            # Output Validation -> END
            builder.add_edge("output_validation", END)

            self._graph = builder.compile()
            logger.info("LangGraph agent orchestration graph compiled successfully")

        except ImportError:
            logger.info(
                "LangGraph not installed. Using sequential fallback orchestration. "
                "Install with: pip install langgraph>=0.2.0"
            )
        except Exception as e:
            logger.warning(f"LangGraph graph build failed: {e}. Using fallback.")

    # ------------------------------------------------------------------
    # Graph node wrappers (sync wrappers for async agents)
    # ------------------------------------------------------------------

    async def _run_safety(self, state: AgentState) -> AgentState:
        return await self.safety.process(state)

    async def _run_intake(self, state: AgentState) -> AgentState:
        return await self.intake.process(state)

    async def _run_documentation(self, state: AgentState) -> AgentState:
        return await self.documentation.process(state)

    async def _run_compliance(self, state: AgentState) -> AgentState:
        return await self.compliance.process(state)

    async def _run_output_validation(self, state: AgentState) -> AgentState:
        return await self.safety.validate_output(state)

    # ------------------------------------------------------------------
    # Conditional routing
    # ------------------------------------------------------------------

    @staticmethod
    def _after_safety(state: AgentState) -> str:
        """Route after safety check."""
        if state.safety_status.is_emergency:
            return "end"
        if state.safety_status.prompt_injection_detected:
            return "end"
        return "intake"

    @staticmethod
    def _after_intake(state: AgentState) -> str:
        """Route after intake processing."""
        if state.ready_for_documentation:
            return "documentation"
        return "end"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_turn(
        self,
        session_id: str,
        user_input: str,
        mode: str = "patient",
        existing_state: Optional[AgentState] = None,
    ) -> AgentState:
        """Process a single conversation turn through the agent pipeline.

        Args:
            session_id: Conversation session ID.
            user_input: User's text input for this turn.
            mode: Conversation mode (patient/clinician/ambient).
            existing_state: Previous state to continue from.

        Returns:
            Updated AgentState with response and all agent outputs.
        """
        # Initialize or restore state
        if existing_state:
            state = existing_state
        else:
            state = AgentState(
                session_id=session_id,
                conversation_mode=mode,
            )

        state.current_input = user_input
        state.completed_agents = []

        # Execute via LangGraph if available, otherwise sequential fallback
        if self._graph is not None:
            try:
                result = await self._graph.ainvoke(state)
                if isinstance(result, AgentState):
                    return result
                # LangGraph may return a dict
                if isinstance(result, dict):
                    return AgentState(**result)
            except Exception as e:
                logger.warning(f"LangGraph execution failed: {e}. Using fallback.")

        # Sequential fallback
        return await self._sequential_execution(state)

    async def _sequential_execution(self, state: AgentState) -> AgentState:
        """Fallback: run agents sequentially without LangGraph."""
        # 1. Safety check
        state = await self.safety.process(state)

        if state.safety_status.is_emergency or state.safety_status.prompt_injection_detected:
            return state

        # 2. Intake processing
        state = await self.intake.process(state)

        # 3. Documentation (if ready)
        if state.ready_for_documentation:
            state = await self.documentation.process(state)

            # 4. Compliance (after documentation)
            if AgentRole.DOCUMENTATION in state.completed_agents:
                state = await self.compliance.process(state)

            # 5. Output validation
            state = await self.safety.validate_output(state)

        return state

    async def process_ambient_chunk(
        self,
        session_id: str,
        transcript_segment: str,
        speaker: str,
        timestamp: float,
        existing_state: Optional[AgentState] = None,
    ) -> AgentState:
        """Process a chunk of ambient recording.

        In ambient mode, segments arrive continuously with speaker labels.
        The orchestrator accumulates context and generates incremental
        SOAP updates.

        Args:
            session_id: Session identifier.
            transcript_segment: Transcribed text for this segment.
            speaker: Speaker label from diarization.
            timestamp: Segment timestamp in seconds.
            existing_state: Accumulated state from previous chunks.

        Returns:
            Updated AgentState.
        """
        if existing_state:
            state = existing_state
        else:
            state = AgentState(
                session_id=session_id,
                conversation_mode="ambient",
            )

        # Append diarized segment
        state.clinical_context.diarized_segments.append({
            "speaker": speaker,
            "text": transcript_segment,
            "timestamp": timestamp,
        })

        # Append to transcript
        state.clinical_context.transcript += f" [{speaker}]: {transcript_segment}"

        # Run safety on each segment
        state.current_input = transcript_segment
        state.completed_agents = []
        state = await self.safety.process(state)

        if state.safety_status.is_emergency:
            return state

        # Extract entities from segment
        state = await self.intake.process(state)

        # In ambient mode, generate documentation periodically
        # (e.g., every 5 minutes of accumulated transcript)
        transcript_length = len(state.clinical_context.transcript)
        if transcript_length > 2000 and not state.ready_for_documentation:
            state.ready_for_documentation = True

        if state.ready_for_documentation:
            state = await self.documentation.process(state)
            if AgentRole.DOCUMENTATION in state.completed_agents:
                state = await self.compliance.process(state)
            # Reset for next increment
            state.ready_for_documentation = False

        return state


# Singleton
_orchestrator: Optional[AgentOrchestrator] = None


def get_agent_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
