"""
Piper TTS Service — Text-to-Speech for the AI Voice Assistant.

Uses Piper TTS (ONNX-based, local, HIPAA-safe) as primary engine
with Web Speech API fallback handled on the client side.
"""

import io
import json
import logging
import struct
import wave
from pathlib import Path
from typing import AsyncGenerator, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded singleton
_tts_service: Optional["PiperTTSService"] = None


class PiperTTSService:
    """Local TTS using Piper (ONNX runtime)."""

    def __init__(self):
        self._model = None
        self._config = None
        self._loaded = False

    def _load_model(self):
        """Lazy-load the Piper TTS model on first use."""
        if self._loaded:
            return

        model_path = Path(settings.piper_model_path)
        config_path = Path(settings.piper_config_path)

        if not model_path.exists():
            logger.warning(
                f"Piper model not found at {model_path}. "
                "TTS will return text-only responses (client uses Web Speech API fallback)."
            )
            self._loaded = True
            return

        try:
            import onnxruntime as ort
            # Load ONNX model
            self._ort_session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )

            # Load config for sample rate and phoneme settings
            if config_path.exists():
                with open(config_path, "r") as f:
                    self._config = json.load(f)
                self._sample_rate = self._config.get("audio", {}).get(
                    "sample_rate", settings.tts_sample_rate
                )
            else:
                self._sample_rate = settings.tts_sample_rate

            # Try loading piper-phonemize for text-to-phoneme conversion
            try:
                from piper_phonemize import phonemize_espeak
                self._phonemize = phonemize_espeak
            except ImportError:
                self._phonemize = None
                logger.warning(
                    "piper-phonemize not available. "
                    "Using piper-tts subprocess fallback."
                )

            self._model = self._ort_session
            self._loaded = True
            logger.info(
                f"Piper TTS loaded: {model_path.name}, "
                f"sample_rate={self._sample_rate}"
            )

        except ImportError:
            logger.warning(
                "onnxruntime not installed. TTS will use text-only mode "
                "(client falls back to Web Speech API)."
            )
            self._loaded = True
        except Exception as e:
            logger.error(f"Failed to load Piper TTS: {e}")
            self._loaded = True

    @property
    def is_available(self) -> bool:
        """Check if TTS model is loaded and ready."""
        self._load_model()
        return self._model is not None

    def synthesize(self, text: str) -> Optional[bytes]:
        """
        Synthesize text to WAV audio bytes.

        Returns None if Piper is not available (client should use Web Speech API).
        """
        self._load_model()

        if not self._model:
            return None

        if not text or not text.strip():
            return None

        # Truncate to max length
        if len(text) > settings.tts_max_text_length:
            text = text[:settings.tts_max_text_length]

        try:
            # Try using piper-tts Python package directly
            return self._synthesize_with_piper_package(text)
        except Exception:
            try:
                # Fallback: use piper CLI subprocess
                return self._synthesize_with_subprocess(text)
            except Exception as e:
                logger.error(f"TTS synthesis failed: {e}")
                return None

    def _synthesize_with_piper_package(self, text: str) -> Optional[bytes]:
        """Synthesize using piper-tts Python package."""
        try:
            from piper import PiperVoice

            voice = PiperVoice.load(
                settings.piper_model_path,
                config_path=settings.piper_config_path,
            )

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                voice.synthesize(text, wav_file)

            return wav_buffer.getvalue()
        except ImportError:
            raise  # Let caller try subprocess fallback

    def _synthesize_with_subprocess(self, text: str) -> Optional[bytes]:
        """Synthesize using piper CLI as subprocess."""
        import subprocess

        try:
            result = subprocess.run(
                [
                    "piper",
                    "--model", settings.piper_model_path,
                    "--config", settings.piper_config_path,
                    "--output-raw",
                ],
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.error(f"Piper CLI error: {result.stderr.decode()}")
                return None

            # Convert raw PCM to WAV
            raw_audio = result.stdout
            return self._pcm_to_wav(raw_audio)
        except FileNotFoundError:
            logger.warning("Piper CLI not found in PATH")
            return None

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Convert raw PCM int16 data to WAV format."""
        sample_rate = getattr(self, "_sample_rate", settings.tts_sample_rate)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_buffer.getvalue()

    async def synthesize_streaming(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text sentence-by-sentence for low time-to-first-byte.

        Yields WAV audio chunks for each sentence.
        """
        import re

        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            audio = self.synthesize(sentence)
            if audio:
                yield audio


def get_tts_service() -> PiperTTSService:
    """Get or create the singleton TTS service."""
    global _tts_service
    if _tts_service is None:
        _tts_service = PiperTTSService()
    return _tts_service
