"""
Pydantic models for AI Voice Assistant conversation state and messaging.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    """Dialogue state machine states."""
    GREETING = "greeting"
    CHIEF_COMPLAINT = "chief_complaint"
    SYMPTOM_DETAILS = "symptom_details"
    FOLLOW_UP = "follow_up"
    SUMMARY = "summary"
    EMERGENCY_ESCALATION = "emergency_escalation"
    ENDED = "ended"


class ConversationMode(str, Enum):
    """Who is using the voice assistant."""
    PATIENT = "patient"
    CLINICIAN = "clinician"


class ConversationTurn(BaseModel):
    """A single turn in the conversation."""
    role: str  # "assistant" or "user"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    state: Optional[ConversationState] = None
    entities_extracted: Optional[Dict[str, Any]] = None


class AssistantResponse(BaseModel):
    """Response from the dialogue manager for a single turn."""
    text: str
    state: ConversationState
    previous_state: Optional[ConversationState] = None
    entities_update: Optional[Dict[str, Any]] = None
    is_final: bool = False
    is_emergency: bool = False
    rag_grounded: bool = False
    documentation: Optional[Dict[str, Any]] = None


class ConversationSessionData(BaseModel):
    """In-memory conversation session state."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: ConversationMode = ConversationMode.PATIENT
    state: ConversationState = ConversationState.GREETING
    turns: List[ConversationTurn] = Field(default_factory=list)
    extracted_entities: Dict[str, Any] = Field(default_factory=lambda: {
        "conditions": [],
        "medications": [],
    })
    collected_symptoms: Dict[str, Any] = Field(default_factory=dict)
    rag_context: Optional[Dict[str, Any]] = None
    accumulated_transcript: str = ""
    followup_round: int = 0
    language: str = "en"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def add_turn(self, role: str, content: str, **kwargs):
        """Add a conversation turn."""
        turn = ConversationTurn(
            role=role,
            content=content,
            state=self.state,
            **kwargs,
        )
        self.turns.append(turn)
        if role == "user":
            self.accumulated_transcript += f" {content}" if self.accumulated_transcript else content

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Get conversation history formatted for LLM chat template."""
        return [
            {"role": t.role, "content": t.content}
            for t in self.turns
        ]


# WebSocket protocol messages

class WSClientAction(BaseModel):
    """Message from client to server."""
    action: str  # "start", "stop", "text_input", "interrupt"
    mode: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None


class WSServerMessage(BaseModel):
    """Message from server to client."""
    type: str  # "connected", "assistant_text", "assistant_audio", "user_transcript",
               # "entities_update", "state_change", "summary", "error"
    session_id: Optional[str] = None
    text: Optional[str] = None
    audio: Optional[str] = None  # base64-encoded WAV
    format: Optional[str] = None
    sample_rate: Optional[int] = None
    state: Optional[str] = None
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    entities: Optional[Dict[str, Any]] = None
    documentation: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    is_final: bool = False
    is_emergency: bool = False
    rag_grounded: bool = False
