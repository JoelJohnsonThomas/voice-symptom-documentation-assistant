"""
Streaming ASR Service - Real-Time Chunked Transcription

Wraps MedASR for pseudo-streaming: accumulates audio chunks in a buffer
and re-transcribes at intervals, returning only the delta (new words).

This is a standard pattern for making batch ASR models (CTC/Transducer)
behave in a streaming fashion without requiring a natively streaming model.
"""

import numpy as np
import time
import logging
import asyncio
from typing import Optional, Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class StreamingASRSession:
    """
    A single streaming transcription session.

    Accumulates raw PCM audio chunks and provides incremental
    transcription results by diffing against previous output.
    """

    def __init__(self, sample_rate: int = None, interval_seconds: float = None):
        """
        Initialize a streaming session.

        Args:
            sample_rate: Audio sample rate (default from settings)
            interval_seconds: How often to run transcription (default 2.0s)
        """
        self.sample_rate = sample_rate or settings.audio_sample_rate
        self.interval_seconds = interval_seconds or getattr(
            settings, 'streaming_interval_seconds', 2.0
        )

        # Audio buffer (accumulated PCM float32 samples)
        self._audio_buffer = np.array([], dtype=np.float32)

        # Transcription state
        self._last_transcript = ""
        self._last_transcribe_time = 0.0
        self._chunk_count = 0
        self._is_finalized = False

        logger.info(
            f"StreamingASRSession created: sr={self.sample_rate}, "
            f"interval={self.interval_seconds}s"
        )

    def add_audio_chunk(self, audio_bytes: bytes) -> None:
        """
        Add a chunk of raw audio data to the buffer.

        Expects raw PCM float32 little-endian samples at the configured
        sample rate, OR WebM/WAV encoded data that will be decoded.

        Args:
            audio_bytes: Raw audio bytes from the browser
        """
        try:
            # Try to decode as PCM float32 first
            chunk = np.frombuffer(audio_bytes, dtype=np.float32)

            if len(chunk) > 0:
                self._audio_buffer = np.concatenate([self._audio_buffer, chunk])
                self._chunk_count += 1

        except Exception as e:
            logger.warning(f"Failed to process audio chunk: {e}")

    def add_audio_array(self, audio_array: np.ndarray) -> None:
        """
        Add decoded audio samples directly.

        Args:
            audio_array: Float32 numpy array of audio samples
        """
        if len(audio_array) > 0:
            self._audio_buffer = np.concatenate([
                self._audio_buffer,
                audio_array.astype(np.float32)
            ])
            self._chunk_count += 1

    def should_transcribe(self) -> bool:
        """Check if enough time has passed to run a new transcription."""
        if self._is_finalized:
            return False

        # Need at least 0.5 seconds of audio
        buffer_duration = len(self._audio_buffer) / self.sample_rate
        if buffer_duration < 0.5:
            return False

        # Check time since last transcription
        elapsed = time.time() - self._last_transcribe_time
        return elapsed >= self.interval_seconds

    def transcribe_partial(self) -> Optional[Dict[str, Any]]:
        """
        Run transcription on accumulated buffer and return delta.

        Returns:
            Dict with type, text (delta), and full_text, or None if
            no new content.
        """
        if len(self._audio_buffer) < self.sample_rate * 0.5:
            return None

        try:
            from app.models.medasr_service import get_medasr_service

            medasr = get_medasr_service()
            if not medasr.is_ready():
                logger.warning("MedASR not ready for streaming transcription")
                return None

            # Transcribe the full buffer
            result = medasr.transcribe(
                audio_array=self._audio_buffer.copy(),
                sample_rate=self.sample_rate
            )
            # transcribe() returns (transcript, language) tuple
            if isinstance(result, tuple):
                full_transcript, _ = result
            else:
                full_transcript = result

            self._last_transcribe_time = time.time()

            # Calculate delta (new words since last transcription)
            delta = self._compute_delta(full_transcript)

            if delta or full_transcript != self._last_transcript:
                self._last_transcript = full_transcript
                return {
                    "type": "partial",
                    "text": delta,
                    "full_text": full_transcript,
                    "duration": len(self._audio_buffer) / self.sample_rate,
                    "chunks_received": self._chunk_count
                }

            return None

        except Exception as e:
            logger.error(f"Streaming transcription failed: {e}")
            return None

    def transcribe_final(self) -> Dict[str, Any]:
        """
        Run final transcription on complete buffer.

        Returns:
            Dict with type="final" and complete transcript.
        """
        self._is_finalized = True

        if len(self._audio_buffer) < self.sample_rate * 0.3:
            logger.warning("Audio buffer too short for final transcription")
            return {
                "type": "final",
                "text": self._last_transcript or "",
                "full_text": self._last_transcript or "",
                "duration": len(self._audio_buffer) / self.sample_rate,
                "chunks_received": self._chunk_count
            }

        try:
            from app.models.medasr_service import get_medasr_service

            medasr = get_medasr_service()
            result = medasr.transcribe(
                audio_array=self._audio_buffer.copy(),
                sample_rate=self.sample_rate
            )
            # transcribe() returns (transcript, language) tuple
            if isinstance(result, tuple):
                full_transcript, _ = result
            else:
                full_transcript = result

            self._last_transcript = full_transcript

            return {
                "type": "final",
                "text": full_transcript,
                "full_text": full_transcript,
                "duration": len(self._audio_buffer) / self.sample_rate,
                "chunks_received": self._chunk_count
            }

        except Exception as e:
            logger.error(f"Final transcription failed: {e}")
            return {
                "type": "final",
                "text": self._last_transcript or "",
                "full_text": self._last_transcript or "",
                "duration": len(self._audio_buffer) / self.sample_rate,
                "chunks_received": self._chunk_count,
                "error": str(e)
            }

    def _compute_delta(self, new_transcript: str) -> str:
        """
        Compute the delta between previous and new transcript.

        Uses word-level comparison to find newly added text.

        Args:
            new_transcript: The latest full transcript

        Returns:
            String containing only the new words
        """
        if not self._last_transcript:
            return new_transcript

        old_words = self._last_transcript.split()
        new_words = new_transcript.split()

        if len(new_words) <= len(old_words):
            # Transcript may have been corrected, return empty delta
            # but the full_text will contain the correction
            if new_transcript != self._last_transcript:
                return ""
            return ""

        # Return the new words appended at the end
        delta_words = new_words[len(old_words):]
        return " ".join(delta_words)

    def get_buffer_duration(self) -> float:
        """Get current buffer duration in seconds."""
        return len(self._audio_buffer) / self.sample_rate

    def get_audio_buffer(self) -> np.ndarray:
        """Get the complete audio buffer (for saving/playback)."""
        return self._audio_buffer.copy()

    def reset(self) -> None:
        """Reset the session for reuse."""
        self._audio_buffer = np.array([], dtype=np.float32)
        self._last_transcript = ""
        self._last_transcribe_time = 0.0
        self._chunk_count = 0
        self._is_finalized = False
