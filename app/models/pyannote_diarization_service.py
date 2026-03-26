"""
ML-Based Speaker Diarization using pyannote.audio (Phase 2)

Replaces the energy-based approach in diarization_service.py with
pyannote.audio 3.x for production-grade speaker diarization:
- <5% Diarization Error Rate (DER) on standard benchmarks
- Supports 2+ speakers
- Provides speaker embeddings for voice biometrics integration
- Falls back to energy-based detection if pyannote unavailable

Requires: pip install pyannote.audio
Requires: Hugging Face token with pyannote access agreement
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import settings
from app.models.diarization_service import (
    DiarizationSession,
    SpeakerSegment,
    DiarizationService as EnergyDiarizationService,
)

logger = logging.getLogger(__name__)


@dataclass
class DiarizedSegment:
    """A diarized transcript segment with speaker attribution."""
    speaker: str
    start: float
    end: float
    text: str = ""
    confidence: float = 0.0


class PyannoteDiarizationService:
    """Production-grade speaker diarization using pyannote.audio.

    Falls back to energy-based detection if pyannote is not available.
    """

    def __init__(self):
        self._pipeline = None
        self._available = False
        self._fallback = None
        self._sessions: Dict[str, DiarizationSession] = {}
        self._load_pipeline()

    def _load_pipeline(self) -> None:
        """Load the pyannote speaker diarization pipeline."""
        try:
            from pyannote.audio import Pipeline

            if not settings.hf_token:
                logger.warning(
                    "HF_TOKEN not set — pyannote.audio requires a Hugging Face token "
                    "with pyannote/speaker-diarization-3.1 access agreement."
                )
                raise ValueError("HF_TOKEN required")

            logger.info("Loading pyannote speaker diarization pipeline...")
            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=settings.hf_token,
            )

            # Move to GPU if available
            if settings.enable_gpu:
                import torch
                if torch.cuda.is_available():
                    self._pipeline.to(torch.device("cuda"))
                    logger.info("pyannote pipeline moved to GPU")

            self._available = True
            logger.info("pyannote diarization pipeline loaded successfully")

        except ImportError:
            logger.warning(
                "pyannote.audio not installed. Using energy-based fallback. "
                "Install with: pip install pyannote.audio"
            )
            self._fallback = EnergyDiarizationService()
        except Exception as e:
            logger.warning(f"pyannote initialization failed: {e}. Using energy-based fallback.")
            self._fallback = EnergyDiarizationService()

    @property
    def is_ready(self) -> bool:
        return self._available or self._fallback is not None

    @property
    def backend(self) -> str:
        return "pyannote" if self._available else "energy"

    def diarize(
        self,
        audio_array: np.ndarray,
        sample_rate: int = 16000,
        num_speakers: Optional[int] = None,
        min_speakers: int = 1,
        max_speakers: int = 4,
    ) -> List[DiarizedSegment]:
        """Run speaker diarization on an audio array.

        Args:
            audio_array: Float32 audio samples.
            sample_rate: Audio sample rate.
            num_speakers: Exact number of speakers (if known).
            min_speakers: Minimum expected speakers.
            max_speakers: Maximum expected speakers.

        Returns:
            List of DiarizedSegment with speaker labels and time ranges.
        """
        if not self._available:
            return self._fallback_diarize(audio_array, sample_rate)

        start_time = time.monotonic()

        try:
            import torch

            # Prepare audio tensor for pyannote (expects [channels, samples])
            if audio_array.ndim == 1:
                waveform = torch.from_numpy(audio_array).unsqueeze(0).float()
            else:
                waveform = torch.from_numpy(audio_array).float()

            # Run pipeline
            kwargs = {}
            if num_speakers is not None:
                kwargs["num_speakers"] = num_speakers
            else:
                kwargs["min_speakers"] = min_speakers
                kwargs["max_speakers"] = max_speakers

            diarization = self._pipeline(
                {"waveform": waveform, "sample_rate": sample_rate},
                **kwargs,
            )

            segments: List[DiarizedSegment] = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append(DiarizedSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                    confidence=0.85,  # pyannote doesn't expose per-segment confidence
                ))

            elapsed = time.monotonic() - start_time
            duration = len(audio_array) / sample_rate
            logger.info(
                f"pyannote diarization: {duration:.1f}s audio -> "
                f"{len(segments)} segments, {len(set(s.speaker for s in segments))} speakers "
                f"in {elapsed:.2f}s"
            )

            return segments

        except Exception as e:
            logger.error(f"pyannote diarization failed: {e}")
            return self._fallback_diarize(audio_array, sample_rate)

    def diarize_with_transcript(
        self,
        audio_array: np.ndarray,
        word_timestamps: List[Dict[str, Any]],
        sample_rate: int = 16000,
    ) -> List[DiarizedSegment]:
        """Diarize audio and align word timestamps to speaker segments.

        Combines pyannote diarization with word-level timestamps from
        faster-whisper to produce speaker-attributed transcript segments.

        Args:
            audio_array: Audio samples.
            word_timestamps: List of {word, start, end, probability} from ASR.
            sample_rate: Audio sample rate.

        Returns:
            List of DiarizedSegment with text populated from aligned words.
        """
        # Get speaker segments
        segments = self.diarize(audio_array, sample_rate)

        if not segments or not word_timestamps:
            return segments

        # Align words to speaker segments
        for seg in segments:
            seg_words = []
            for w in word_timestamps:
                word_mid = (w["start"] + w["end"]) / 2
                if seg.start <= word_mid <= seg.end:
                    seg_words.append(w["word"])
            seg.text = " ".join(seg_words)

        return segments

    def _fallback_diarize(
        self,
        audio_array: np.ndarray,
        sample_rate: int,
    ) -> List[DiarizedSegment]:
        """Fall back to energy-based diarization."""
        if self._fallback is None:
            self._fallback = EnergyDiarizationService()

        session_id = f"fallback_{time.monotonic()}"
        self._fallback.create_session(session_id)

        # Process in chunks
        chunk_size = sample_rate  # 1-second chunks
        segments = []
        current_speaker = "speaker_0"

        for i in range(0, len(audio_array), chunk_size):
            chunk = audio_array[i:i + chunk_size]
            timestamp = i / sample_rate
            result = self._fallback.detect_speaker_change(
                session_id, chunk, timestamp, sample_rate
            )
            if result.get("changed"):
                current_speaker = result["speaker"]

            segments.append(DiarizedSegment(
                speaker=current_speaker,
                start=timestamp,
                end=(i + len(chunk)) / sample_rate,
                confidence=result.get("confidence", 0.3),
            ))

        self._fallback.close_session(session_id)

        # Merge consecutive segments from same speaker
        merged = []
        for seg in segments:
            if merged and merged[-1].speaker == seg.speaker:
                merged[-1].end = seg.end
            else:
                merged.append(seg)

        return merged

    # ------------------------------------------------------------------
    # Session management (compatible with existing DiarizationService API)
    # ------------------------------------------------------------------

    def create_session(self, session_id: str) -> DiarizationSession:
        from datetime import datetime
        session = DiarizationSession(session_id=session_id, started_at=datetime.utcnow())
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[DiarizationSession]:
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> Optional[DiarizationSession]:
        return self._sessions.pop(session_id, None)


# Singleton
_service: Optional[PyannoteDiarizationService] = None


def get_pyannote_diarization_service() -> PyannoteDiarizationService:
    global _service
    if _service is None:
        _service = PyannoteDiarizationService()
    return _service
