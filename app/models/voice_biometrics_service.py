"""
Voice Biometrics Service (Phase 2)

Speaker identification using ECAPA-TDNN speaker embeddings for:
- Identifying enrolled clinicians vs. unknown patients in ambient mode
- Speaker re-identification across sessions
- Voice-based authentication (supplementary, not primary)

Uses SpeechBrain's ECAPA-TDNN model pre-trained on VoxCeleb.
Falls back gracefully if SpeechBrain is not installed.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SpeakerProfile:
    """Enrolled speaker profile with embedding."""
    speaker_id: str
    name: str
    role: str  # "clinician", "patient", "other"
    embedding: np.ndarray = field(repr=False)
    enrolled_at: float = 0.0
    sample_count: int = 1


@dataclass
class IdentificationResult:
    """Result of a speaker identification attempt."""
    speaker_id: Optional[str]
    name: Optional[str]
    role: Optional[str]
    confidence: float
    is_enrolled: bool


class VoiceBiometricsService:
    """Speaker identification using ECAPA-TDNN embeddings.

    Enrollment: capture 10-30 seconds of speech per speaker.
    Identification: compare embedding against enrolled profiles.
    """

    def __init__(self):
        self._model = None
        self._available = False
        self._profiles: Dict[str, SpeakerProfile] = {}
        self._similarity_threshold = 0.7  # Cosine similarity threshold
        self._load_model()

    def _load_model(self) -> None:
        """Load SpeechBrain ECAPA-TDNN speaker embedding model."""
        try:
            from speechbrain.inference.speaker import EncoderClassifier

            logger.info("Loading SpeechBrain ECAPA-TDNN speaker embedding model...")
            self._model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir="./models/speechbrain_ecapa",
                run_opts={"device": "cuda" if settings.enable_gpu else "cpu"},
            )
            self._available = True
            logger.info("Voice biometrics model loaded successfully")

        except ImportError:
            logger.warning(
                "speechbrain not installed. Voice biometrics unavailable. "
                "Install with: pip install speechbrain"
            )
        except Exception as e:
            logger.warning(f"Voice biometrics initialization failed: {e}")

    @property
    def is_ready(self) -> bool:
        return self._available

    def extract_embedding(self, audio_array: np.ndarray, sample_rate: int = 16000) -> Optional[np.ndarray]:
        """Extract a speaker embedding from an audio segment.

        Args:
            audio_array: Float32 audio samples (ideally 5-30 seconds).
            sample_rate: Audio sample rate.

        Returns:
            Numpy array of speaker embedding, or None if extraction fails.
        """
        if not self._available or self._model is None:
            return None

        try:
            import torch

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                import torchaudio
                waveform = torch.from_numpy(audio_array).unsqueeze(0).float()
                waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
            else:
                waveform = torch.from_numpy(audio_array).unsqueeze(0).float()

            # Extract embedding
            embedding = self._model.encode_batch(waveform)
            return embedding.squeeze().cpu().numpy()

        except Exception as e:
            logger.error(f"Embedding extraction failed: {e}")
            return None

    def enroll_speaker(
        self,
        speaker_id: str,
        name: str,
        role: str,
        audio_array: np.ndarray,
        sample_rate: int = 16000,
    ) -> bool:
        """Enroll a new speaker or update an existing enrollment.

        Args:
            speaker_id: Unique identifier for the speaker.
            name: Display name.
            role: Speaker role ("clinician", "patient", etc.).
            audio_array: Enrollment audio (10-30 seconds recommended).
            sample_rate: Audio sample rate.

        Returns:
            True if enrollment succeeded.
        """
        embedding = self.extract_embedding(audio_array, sample_rate)
        if embedding is None:
            logger.warning(f"Failed to enroll speaker {speaker_id}: embedding extraction failed")
            return False

        # If already enrolled, update with averaged embedding
        if speaker_id in self._profiles:
            existing = self._profiles[speaker_id]
            count = existing.sample_count
            existing.embedding = (existing.embedding * count + embedding) / (count + 1)
            existing.sample_count += 1
            logger.info(f"Updated speaker enrollment: {speaker_id} (samples: {existing.sample_count})")
        else:
            self._profiles[speaker_id] = SpeakerProfile(
                speaker_id=speaker_id,
                name=name,
                role=role,
                embedding=embedding,
                enrolled_at=time.time(),
            )
            logger.info(f"Enrolled new speaker: {speaker_id} ({name}, {role})")

        return True

    def identify_speaker(
        self,
        audio_array: np.ndarray,
        sample_rate: int = 16000,
    ) -> IdentificationResult:
        """Identify a speaker from an audio segment.

        Args:
            audio_array: Audio segment to identify (at least 2 seconds).
            sample_rate: Audio sample rate.

        Returns:
            IdentificationResult with speaker info and confidence.
        """
        if not self._available or not self._profiles:
            return IdentificationResult(
                speaker_id=None, name=None, role=None,
                confidence=0.0, is_enrolled=False,
            )

        embedding = self.extract_embedding(audio_array, sample_rate)
        if embedding is None:
            return IdentificationResult(
                speaker_id=None, name=None, role=None,
                confidence=0.0, is_enrolled=False,
            )

        # Compare against all enrolled profiles
        best_match: Optional[SpeakerProfile] = None
        best_score = -1.0

        for profile in self._profiles.values():
            score = self._cosine_similarity(embedding, profile.embedding)
            if score > best_score:
                best_score = score
                best_match = profile

        if best_match is not None and best_score >= self._similarity_threshold:
            return IdentificationResult(
                speaker_id=best_match.speaker_id,
                name=best_match.name,
                role=best_match.role,
                confidence=float(best_score),
                is_enrolled=True,
            )

        return IdentificationResult(
            speaker_id=None, name=None, role=None,
            confidence=float(best_score) if best_score > 0 else 0.0,
            is_enrolled=False,
        )

    def get_enrolled_speakers(self) -> List[Dict]:
        """List all enrolled speaker profiles (without embeddings)."""
        return [
            {
                "speaker_id": p.speaker_id,
                "name": p.name,
                "role": p.role,
                "sample_count": p.sample_count,
            }
            for p in self._profiles.values()
        ]

    def remove_speaker(self, speaker_id: str) -> bool:
        """Remove an enrolled speaker profile."""
        if speaker_id in self._profiles:
            del self._profiles[speaker_id]
            return True
        return False

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))


# Singleton
_service: Optional[VoiceBiometricsService] = None


def get_voice_biometrics_service() -> VoiceBiometricsService:
    global _service
    if _service is None:
        _service = VoiceBiometricsService()
    return _service
