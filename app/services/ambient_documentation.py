"""
Ambient Clinical Documentation Mode (Phase 3)

Passively listens to a clinician-patient encounter and generates
a structured SOAP note in real-time. Unlike the interactive intake
flow, ambient mode:

- Does NOT ask follow-up questions
- Continuously accumulates diarized transcript segments
- Periodically generates incremental SOAP updates
- Distinguishes clinician vs patient speech for Subjective/Objective split
- Flags emergencies but does not interrupt the conversation

Architecture:
    Audio stream → faster-whisper (streaming ASR)
                 → pyannote (diarization)
                 → AmbientDocumentationSession (this module)
                 → Agent Orchestrator (ambient mode)
                 → Incremental SOAP output via WebSocket
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.conversation_session import ConversationMode

logger = logging.getLogger(__name__)


# Minimum transcript length (chars) before triggering SOAP generation
_MIN_TRANSCRIPT_FOR_SOAP = 200

# Time (seconds) between incremental SOAP regeneration
_SOAP_UPDATE_INTERVAL = 60.0


@dataclass
class DiarizedSegment:
    """A single diarized transcript segment."""
    speaker: str          # "clinician", "patient", or "unknown"
    text: str
    start_time: float     # Seconds from encounter start
    end_time: float
    confidence: float = 1.0


@dataclass
class AmbientSOAPSnapshot:
    """Point-in-time SOAP snapshot with version tracking."""
    version: int
    timestamp: float
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""
    transcript_length: int = 0
    segment_count: int = 0
    confidence: Dict[str, float] = field(default_factory=dict)


class AmbientDocumentationSession:
    """Manages a single ambient documentation encounter.

    Usage:
        session = AmbientDocumentationSession(session_id="abc-123")
        await session.start()

        # As diarized segments arrive from ASR pipeline:
        snapshot = await session.add_segment(
            speaker="patient",
            text="I've been having chest pain for two days",
            start_time=12.5,
            end_time=18.3,
        )

        # Get current SOAP state at any time:
        soap = session.get_current_soap()

        # End encounter:
        final = await session.finalize()
    """

    def __init__(
        self,
        session_id: str,
        language: str = "en",
        auto_detect_specialty: bool = True,
    ):
        self.session_id = session_id
        self.language = language
        self.auto_detect_specialty = auto_detect_specialty

        self.segments: List[DiarizedSegment] = []
        self.soap_snapshots: List[AmbientSOAPSnapshot] = []
        self.detected_specialty: str = "general"
        self.encounter_start: Optional[float] = None
        self.encounter_end: Optional[float] = None

        self._orchestrator = None
        self._agent_state = None
        self._last_soap_time: float = 0
        self._soap_version: int = 0
        self._is_active: bool = False

    async def start(self) -> None:
        """Start the ambient documentation session."""
        self.encounter_start = time.time()
        self._is_active = True
        self._init_orchestrator()
        logger.info(f"Ambient session {self.session_id} started")

    def _init_orchestrator(self) -> None:
        """Lazy-init the agent orchestrator."""
        try:
            from app.services.agent_orchestrator import (
                AgentOrchestrator,
                AgentState,
                ClinicalContext,
            )
            self._orchestrator = AgentOrchestrator()
            self._agent_state = AgentState(
                session_id=self.session_id,
                conversation_mode="ambient",
                clinical_context=ClinicalContext(
                    detected_language=self.language,
                ),
            )
        except Exception as e:
            logger.warning(f"Orchestrator init failed: {e}. Using standalone mode.")

    async def add_segment(
        self,
        speaker: str,
        text: str,
        start_time: float,
        end_time: float,
        confidence: float = 1.0,
    ) -> Optional[AmbientSOAPSnapshot]:
        """Add a new diarized transcript segment.

        Args:
            speaker: "clinician", "patient", or "unknown".
            text: Transcribed text for this segment.
            start_time: Segment start time (seconds from encounter start).
            end_time: Segment end time.
            confidence: ASR confidence for this segment.

        Returns:
            An updated SOAP snapshot if a regeneration was triggered,
            otherwise None.
        """
        if not self._is_active:
            return None

        segment = DiarizedSegment(
            speaker=speaker,
            text=text.strip(),
            start_time=start_time,
            end_time=end_time,
            confidence=confidence,
        )
        self.segments.append(segment)

        # Auto-detect specialty from first substantial patient segment
        if (
            self.auto_detect_specialty
            and self.detected_specialty == "general"
            and speaker == "patient"
            and len(text) > 20
        ):
            self._detect_specialty(text)

        # Check if SOAP regeneration is due
        now = time.time()
        transcript_len = sum(len(s.text) for s in self.segments)
        time_elapsed = now - self._last_soap_time

        if (
            transcript_len >= _MIN_TRANSCRIPT_FOR_SOAP
            and time_elapsed >= _SOAP_UPDATE_INTERVAL
        ):
            return await self._generate_soap_update()

        return None

    async def force_soap_update(self) -> AmbientSOAPSnapshot:
        """Force an immediate SOAP regeneration regardless of interval."""
        return await self._generate_soap_update()

    async def finalize(self) -> AmbientSOAPSnapshot:
        """End the ambient session and produce the final SOAP note."""
        self.encounter_end = time.time()
        self._is_active = False

        # Generate final SOAP
        final = await self._generate_soap_update()

        duration = (self.encounter_end - self.encounter_start) if self.encounter_start else 0
        logger.info(
            f"Ambient session {self.session_id} finalized: "
            f"{len(self.segments)} segments, "
            f"{duration:.0f}s duration, "
            f"specialty={self.detected_specialty}, "
            f"SOAP versions={self._soap_version}"
        )

        return final

    def get_current_soap(self) -> Optional[AmbientSOAPSnapshot]:
        """Get the most recent SOAP snapshot."""
        return self.soap_snapshots[-1] if self.soap_snapshots else None

    def get_patient_transcript(self) -> str:
        """Get only patient-spoken segments as a single transcript."""
        return " ".join(
            s.text for s in self.segments if s.speaker == "patient"
        )

    def get_clinician_transcript(self) -> str:
        """Get only clinician-spoken segments."""
        return " ".join(
            s.text for s in self.segments if s.speaker == "clinician"
        )

    def get_full_transcript(self) -> str:
        """Get the full transcript with speaker labels."""
        return "\n".join(
            f"[{s.speaker.upper()} {s.start_time:.1f}s]: {s.text}"
            for s in self.segments
        )

    async def _generate_soap_update(self) -> AmbientSOAPSnapshot:
        """Generate an incremental SOAP update from accumulated segments."""
        self._soap_version += 1
        self._last_soap_time = time.time()

        patient_text = self.get_patient_transcript()
        clinician_text = self.get_clinician_transcript()

        # Use orchestrator if available
        if self._orchestrator and self._agent_state:
            try:
                self._agent_state = await self._orchestrator.process_ambient_chunk(
                    session_id=self.session_id,
                    transcript_segment=patient_text,
                    speaker="patient",
                    timestamp=time.time() - (self.encounter_start or time.time()),
                    existing_state=self._agent_state,
                )

                doc = self._agent_state.documentation
                snapshot = AmbientSOAPSnapshot(
                    version=self._soap_version,
                    timestamp=time.time(),
                    subjective=doc.soap_subjective,
                    objective=doc.soap_objective,
                    assessment=doc.soap_assessment,
                    plan=doc.soap_plan,
                    transcript_length=len(patient_text),
                    segment_count=len(self.segments),
                    confidence=doc.confidence,
                )
                self.soap_snapshots.append(snapshot)
                return snapshot

            except Exception as e:
                logger.warning(f"Orchestrator SOAP generation failed: {e}")

        # Standalone fallback: use MedGemma directly
        snapshot = await self._standalone_soap_generation(patient_text, clinician_text)
        self.soap_snapshots.append(snapshot)
        return snapshot

    async def _standalone_soap_generation(
        self, patient_text: str, clinician_text: str
    ) -> AmbientSOAPSnapshot:
        """Generate SOAP using MedGemma directly without orchestrator."""
        try:
            from app.models.medgemma_service import get_medgemma_service
            medgemma = get_medgemma_service()

            result = medgemma.generate_documentation(
                transcript=patient_text,
                detected_language=self.language,
            )

            return AmbientSOAPSnapshot(
                version=self._soap_version,
                timestamp=time.time(),
                subjective=result.get("soap_note_subjective", ""),
                objective=result.get("soap_note_objective", ""),
                assessment=result.get("soap_note_assessment", ""),
                plan=result.get("soap_note_plan", ""),
                transcript_length=len(patient_text),
                segment_count=len(self.segments),
                confidence=result.get("field_confidence", {}),
            )

        except Exception as e:
            logger.error(f"Standalone SOAP generation failed: {e}")
            return AmbientSOAPSnapshot(
                version=self._soap_version,
                timestamp=time.time(),
                subjective=f"Patient reports: {patient_text[:500]}",
                objective=f"Clinician notes: {clinician_text[:500]}",
                assessment="Pending — ambient documentation generation failed.",
                plan="Pending — requires manual documentation.",
                transcript_length=len(patient_text),
                segment_count=len(self.segments),
            )

    def _detect_specialty(self, patient_text: str) -> None:
        """Auto-detect clinical specialty from patient speech."""
        try:
            from app.prompts.specialty import detect_specialty
            self.detected_specialty = detect_specialty(patient_text)
            if self.detected_specialty != "general":
                logger.info(
                    f"Ambient session {self.session_id}: "
                    f"auto-detected specialty={self.detected_specialty}"
                )
        except Exception:
            pass


# Active session registry
_ambient_sessions: Dict[str, AmbientDocumentationSession] = {}


def get_ambient_session(session_id: str) -> Optional[AmbientDocumentationSession]:
    """Get an active ambient session by ID."""
    return _ambient_sessions.get(session_id)


async def create_ambient_session(
    session_id: str,
    language: str = "en",
) -> AmbientDocumentationSession:
    """Create and start a new ambient documentation session."""
    session = AmbientDocumentationSession(
        session_id=session_id,
        language=language,
    )
    await session.start()
    _ambient_sessions[session_id] = session
    return session


async def end_ambient_session(session_id: str) -> Optional[AmbientSOAPSnapshot]:
    """End an ambient session and return the final SOAP note."""
    session = _ambient_sessions.pop(session_id, None)
    if session:
        return await session.finalize()
    return None
