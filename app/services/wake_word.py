"""
Wake Word + Voice Command Support (Phase 4)

Integrates Picovoice Porcupine for wake word detection and voice
command recognition for hands-free clinical workflow.

Commands:
- "Hey Triage" → Activate listening
- "Start documentation" → Begin ambient mode
- "Stop documentation" → Finalize encounter
- "Read back" → TTS playback of current SOAP
- "Next patient" → End session, clear context
- "Emergency" → Trigger safety escalation

Falls back to a keyword-spotting approach if Picovoice is unavailable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VoiceCommand(str, Enum):
    """Recognized voice commands."""
    WAKE = "wake"
    START_DOCUMENTATION = "start_documentation"
    STOP_DOCUMENTATION = "stop_documentation"
    READ_BACK = "read_back"
    NEXT_PATIENT = "next_patient"
    EMERGENCY = "emergency"
    REPEAT = "repeat"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class CommandResult:
    """Result of voice command detection."""
    detected: bool
    command: VoiceCommand
    confidence: float = 0.0
    raw_text: str = ""


# Command patterns for keyword-based fallback detection
_COMMAND_PATTERNS = {
    VoiceCommand.START_DOCUMENTATION: [
        r"\bstart\s+(documentation|recording|encounter|session)\b",
        r"\bbegin\s+(documentation|recording|encounter)\b",
    ],
    VoiceCommand.STOP_DOCUMENTATION: [
        r"\bstop\s+(documentation|recording|encounter|session)\b",
        r"\bend\s+(documentation|recording|encounter|session)\b",
        r"\bfinalize\b",
    ],
    VoiceCommand.READ_BACK: [
        r"\bread\s*(it\s+)?back\b",
        r"\bplay\s*back\b",
        r"\bread\s+soap\b",
        r"\bsummar(y|ize)\b",
    ],
    VoiceCommand.NEXT_PATIENT: [
        r"\bnext\s+patient\b",
        r"\bnew\s+patient\b",
        r"\bclear\s+session\b",
    ],
    VoiceCommand.EMERGENCY: [
        r"\bemergency\b",
        r"\bcode\s+(blue|red)\b",
        r"\bcall\s+911\b",
    ],
    VoiceCommand.REPEAT: [
        r"\brepeat\b",
        r"\bsay\s+(?:that\s+)?again\b",
    ],
    VoiceCommand.HELP: [
        r"\bhelp\b",
        r"\bwhat\s+can\s+(?:you|I)\s+(?:do|say)\b",
    ],
}


class WakeWordDetector:
    """Wake word and voice command detector.

    Uses Picovoice Porcupine for wake word detection with a
    regex-based fallback for command recognition from transcripts.
    """

    def __init__(
        self,
        access_key: Optional[str] = None,
        wake_words: Optional[List[str]] = None,
    ):
        self._porcupine = None
        self._available = False
        self._wake_words = wake_words or ["hey triage", "okay triage"]
        self._access_key = access_key

        self._init_porcupine()

    def _init_porcupine(self) -> None:
        """Initialize Picovoice Porcupine wake word engine."""
        if not self._access_key:
            logger.info(
                "Picovoice access key not provided. "
                "Using keyword-based fallback for voice commands."
            )
            return

        try:
            import pvporcupine

            self._porcupine = pvporcupine.create(
                access_key=self._access_key,
                keywords=["computer"],  # Built-in keyword as fallback
            )
            self._available = True
            logger.info("Picovoice Porcupine wake word engine initialized")

        except ImportError:
            logger.info(
                "pvporcupine not installed. Using keyword fallback. "
                "Install with: pip install pvporcupine>=3.0.0"
            )
        except Exception as e:
            logger.warning(f"Porcupine init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    def detect_wake_word_audio(self, audio_frame: bytes) -> bool:
        """Detect wake word from raw audio frame.

        Args:
            audio_frame: PCM audio frame (16-bit, 16kHz).

        Returns:
            True if wake word detected.
        """
        if not self._porcupine:
            return False

        try:
            import struct
            pcm = struct.unpack_from(
                f"{len(audio_frame) // 2}h", audio_frame
            )
            result = self._porcupine.process(pcm)
            return result >= 0
        except Exception as e:
            logger.debug(f"Wake word detection error: {e}")
            return False

    def detect_command_from_text(self, text: str) -> CommandResult:
        """Detect a voice command from transcribed text.

        This is the fallback approach — runs on ASR output instead of
        raw audio.

        Args:
            text: Transcribed text to check for commands.

        Returns:
            CommandResult with detected command.
        """
        text_lower = text.lower().strip()

        # Check wake word
        for wake in self._wake_words:
            if wake in text_lower:
                return CommandResult(
                    detected=True,
                    command=VoiceCommand.WAKE,
                    confidence=0.9,
                    raw_text=text,
                )

        # Check command patterns
        for command, patterns in _COMMAND_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return CommandResult(
                        detected=True,
                        command=command,
                        confidence=0.85,
                        raw_text=text,
                    )

        return CommandResult(
            detected=False,
            command=VoiceCommand.UNKNOWN,
            confidence=0.0,
            raw_text=text,
        )

    def cleanup(self) -> None:
        """Release Porcupine resources."""
        if self._porcupine:
            self._porcupine.delete()
            self._porcupine = None


# Singleton
_detector: Optional[WakeWordDetector] = None


def get_wake_word_detector() -> WakeWordDetector:
    global _detector
    if _detector is None:
        access_key = getattr(settings, "picovoice_access_key", None)
        _detector = WakeWordDetector(access_key=access_key)
    return _detector
