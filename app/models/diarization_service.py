"""
Speaker Diarization Service (Phase 5)

Separates patient vs. clinician speech in ambient documentation mode.
Uses energy-based speaker change detection as a lightweight approach,
with an upgrade path to pyannote.audio for production.

Ambient mode: continuous mic streaming throughout the entire encounter,
not just the patient intake phase.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of speech attributed to a speaker."""
    speaker: str  # "speaker_0", "speaker_1", or "unknown"
    start_time: float  # seconds from session start
    end_time: float
    text: str = ""
    confidence: float = 0.0


@dataclass
class DiarizationSession:
    """Tracks speaker turns within an ambient documentation session."""
    session_id: str
    segments: List[SpeakerSegment] = field(default_factory=list)
    current_speaker: str = "unknown"
    speaker_profiles: Dict[str, Dict] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    _energy_history: List[Tuple[float, float]] = field(default_factory=list)

    def add_segment(self, speaker: str, start: float, end: float, text: str = "", confidence: float = 0.5):
        self.segments.append(SpeakerSegment(
            speaker=speaker, start_time=start, end_time=end,
            text=text, confidence=confidence,
        ))
        self.current_speaker = speaker

    def get_transcript_by_speaker(self) -> Dict[str, str]:
        """Merge segments by speaker into full transcripts."""
        transcripts: Dict[str, List[str]] = {}
        for seg in self.segments:
            transcripts.setdefault(seg.speaker, []).append(seg.text)
        return {spk: " ".join(texts) for spk, texts in transcripts.items()}

    def get_turn_count(self) -> int:
        return len(self.segments)


class DiarizationService:
    """Lightweight speaker diarization using energy-based change detection.

    This is a simple approach suitable for two-speaker clinical encounters.
    For production, replace with pyannote.audio pipeline.
    """

    def __init__(self):
        self._sessions: Dict[str, DiarizationSession] = {}
        self._model_loaded = False
        logger.info("DiarizationService initialized (energy-based mode)")

    def create_session(self, session_id: str) -> DiarizationSession:
        session = DiarizationSession(session_id=session_id, started_at=datetime.utcnow())
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[DiarizationSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> Optional[DiarizationSession]:
        return self._sessions.pop(session_id, None)

    def detect_speaker_change(
        self,
        session_id: str,
        audio_chunk: np.ndarray,
        timestamp: float,
        sample_rate: int = 16000,
    ) -> Dict:
        """Detect if the current audio chunk indicates a speaker change.

        Uses energy envelope and zero-crossing rate as simple features.
        Returns speaker label and confidence.
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"speaker": "unknown", "changed": False, "confidence": 0.0}

        if len(audio_chunk) == 0:
            return {"speaker": session.current_speaker, "changed": False, "confidence": 0.0}

        # Compute energy features
        energy = float(np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2)))
        zcr = float(np.sum(np.abs(np.diff(np.sign(audio_chunk)))) / (2 * len(audio_chunk)))

        session._energy_history.append((energy, zcr))

        # Need at least 5 chunks to detect changes
        if len(session._energy_history) < 5:
            return {"speaker": session.current_speaker, "changed": False, "confidence": 0.3}

        # Simple change detection: significant energy shift
        recent = session._energy_history[-5:]
        prev = session._energy_history[-10:-5] if len(session._energy_history) >= 10 else recent

        recent_energy = np.mean([e for e, _ in recent])
        prev_energy = np.mean([e for e, _ in prev])

        # Energy ratio indicates potential speaker change
        if prev_energy > 0:
            ratio = abs(recent_energy - prev_energy) / max(prev_energy, 1e-6)
        else:
            ratio = 0.0

        changed = ratio > 0.5  # Threshold for speaker change
        confidence = min(ratio, 1.0)

        if changed:
            # Toggle between speaker_0 and speaker_1
            new_speaker = "speaker_1" if session.current_speaker == "speaker_0" else "speaker_0"
            session.current_speaker = new_speaker
        else:
            new_speaker = session.current_speaker

        return {
            "speaker": new_speaker,
            "changed": changed,
            "confidence": confidence,
            "energy": energy,
        }

    def label_transcript_segment(
        self,
        session_id: str,
        text: str,
        start_time: float,
        end_time: float,
        speaker: Optional[str] = None,
    ) -> SpeakerSegment:
        """Label a transcript segment with speaker attribution."""
        session = self._sessions.get(session_id)
        if not session:
            return SpeakerSegment(speaker="unknown", start_time=start_time, end_time=end_time, text=text)

        spk = speaker or session.current_speaker
        session.add_segment(spk, start_time, end_time, text, confidence=0.6)
        return session.segments[-1]

    def get_ambient_summary(self, session_id: str) -> Dict:
        """Get summary of the ambient session for documentation."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}

        transcripts = session.get_transcript_by_speaker()
        return {
            "session_id": session_id,
            "total_segments": len(session.segments),
            "speakers": list(transcripts.keys()),
            "transcripts_by_speaker": transcripts,
            "duration_seconds": (
                session.segments[-1].end_time - session.segments[0].start_time
                if session.segments else 0
            ),
        }


# Singleton
_diarization_service = None


def get_diarization_service() -> DiarizationService:
    global _diarization_service
    if _diarization_service is None:
        _diarization_service = DiarizationService()
    return _diarization_service
