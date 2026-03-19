"""
Voice Activity Detection (VAD) Service — Silero VAD integration.

Provides server-side voice activity detection for the AI Voice Assistant:
- Automatic turn-taking: detect when the patient stops speaking
- Barge-in detection: patient starts speaking while assistant is outputting TTS
- Speech segment extraction: filter out silence for cleaner ASR

Uses Silero VAD (~2MB model, MIT licensed, CPU-friendly, ~1ms per frame).
Falls back to energy-based VAD if Silero is not available.
"""

import logging
import time
from collections import deque
from typing import Optional, Tuple

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_vad_service: Optional["VADService"] = None


class VADService:
    """
    Voice Activity Detection using Silero VAD with energy-based fallback.

    Operates on 16kHz mono float32 audio in 32ms windows (512 samples).
    """

    def __init__(self):
        self._model = None
        self._loaded = False
        self._use_silero = False

        # State tracking
        self._speech_started = False
        self._silence_start: Optional[float] = None
        self._speech_start: Optional[float] = None
        self._recent_probs: deque = deque(maxlen=30)  # ~1 second of history

    def _load_model(self):
        """Lazy-load Silero VAD model."""
        if self._loaded:
            return

        if not settings.vad_enabled:
            self._loaded = True
            return

        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]
            self._use_silero = True
            self._loaded = True
            logger.info("Silero VAD loaded successfully")
        except Exception as e:
            logger.warning(
                f"Silero VAD not available ({e}), using energy-based fallback"
            )
            self._use_silero = False
            self._loaded = True

    @property
    def is_available(self) -> bool:
        """Check if VAD is loaded and enabled."""
        self._load_model()
        return settings.vad_enabled

    def get_speech_probability(self, audio_chunk: np.ndarray,
                                sample_rate: int = 16000) -> float:
        """
        Get speech probability for an audio chunk.

        Args:
            audio_chunk: Float32 audio samples (ideally 512 samples = 32ms at 16kHz)
            sample_rate: Sample rate of the audio

        Returns:
            Speech probability between 0.0 and 1.0
        """
        self._load_model()

        if not settings.vad_enabled:
            return 0.5  # Neutral — neither speech nor silence

        if self._use_silero:
            return self._silero_probability(audio_chunk, sample_rate)
        else:
            return self._energy_probability(audio_chunk)

    def _silero_probability(self, audio_chunk: np.ndarray,
                             sample_rate: int) -> float:
        """Get speech probability using Silero VAD."""
        try:
            import torch
            tensor = torch.from_numpy(audio_chunk).float()

            # Silero expects specific chunk sizes: 256, 512, or 768 at 16kHz
            if len(tensor) < 512:
                tensor = torch.nn.functional.pad(tensor, (0, 512 - len(tensor)))
            elif len(tensor) > 768:
                tensor = tensor[:768]

            prob = self._model(tensor, sample_rate).item()
            self._recent_probs.append(prob)
            return prob
        except Exception as e:
            logger.debug(f"Silero VAD inference failed: {e}")
            return self._energy_probability(audio_chunk)

    @staticmethod
    def _energy_probability(audio_chunk: np.ndarray) -> float:
        """
        Simple energy-based speech detection fallback.

        Computes RMS energy and maps to a [0, 1] probability.
        """
        if len(audio_chunk) == 0:
            return 0.0

        rms = np.sqrt(np.mean(audio_chunk ** 2))
        # Map RMS to probability. Typical speech RMS: 0.02-0.2
        # Silence RMS: <0.005
        prob = min(1.0, max(0.0, (rms - 0.005) / 0.05))
        return prob

    def process_frame(self, audio_chunk: np.ndarray,
                       sample_rate: int = 16000) -> dict:
        """
        Process an audio frame and return VAD state.

        Returns dict with:
            - is_speech: bool — whether current frame is speech
            - speech_prob: float — raw probability
            - turn_ended: bool — silence exceeded threshold (end of turn)
            - barge_in: bool — speech detected after silence (interrupt)
            - speech_duration_ms: int — current speech segment duration
            - silence_duration_ms: int — current silence duration
        """
        prob = self.get_speech_probability(audio_chunk, sample_rate)
        is_speech = prob >= settings.vad_threshold
        now = time.time()

        turn_ended = False
        barge_in = False
        speech_duration_ms = 0
        silence_duration_ms = 0

        if is_speech:
            if not self._speech_started:
                # Speech just started
                self._speech_started = True
                self._speech_start = now
                self._silence_start = None

                # Barge-in: speech after a period of silence
                barge_in = True

            silence_duration_ms = 0
            if self._speech_start:
                speech_duration_ms = int((now - self._speech_start) * 1000)
        else:
            if self._speech_started:
                # Silence after speech
                if self._silence_start is None:
                    self._silence_start = now
                else:
                    silence_duration_ms = int((now - self._silence_start) * 1000)

                    if silence_duration_ms >= settings.vad_min_silence_ms:
                        # Enough silence — turn has ended
                        speech_duration_ms = int(
                            (self._silence_start - (self._speech_start or now)) * 1000
                        )
                        # Only count as valid turn if speech was long enough
                        if speech_duration_ms >= settings.vad_min_speech_ms:
                            turn_ended = True
                        self._speech_started = False
                        self._speech_start = None
                        self._silence_start = None

        return {
            "is_speech": is_speech,
            "speech_prob": round(prob, 3),
            "turn_ended": turn_ended,
            "barge_in": barge_in,
            "speech_duration_ms": speech_duration_ms,
            "silence_duration_ms": silence_duration_ms,
        }

    def get_smoothed_probability(self) -> float:
        """Get smoothed speech probability from recent frames."""
        if not self._recent_probs:
            return 0.0
        return sum(self._recent_probs) / len(self._recent_probs)

    def reset(self):
        """Reset VAD state for a new turn."""
        self._speech_started = False
        self._silence_start = None
        self._speech_start = None
        self._recent_probs.clear()
        if self._use_silero and self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass


def get_vad_service() -> VADService:
    """Get or create the singleton VAD service."""
    global _vad_service
    if _vad_service is None:
        _vad_service = VADService()
    return _vad_service
