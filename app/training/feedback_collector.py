"""
Feedback Collector — Stores clinician corrections for LoRA training.

When a clinician edits an AI-generated SOAP note, this module captures
the (original, corrected) pair with metadata for fine-tuning.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_FEEDBACK_DIR = "training_data/feedback"


@dataclass
class ClinicalFeedback:
    """A single clinician correction to an AI-generated SOAP section."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    clinician_id: str = ""
    clinician_role: str = ""
    timestamp: float = field(default_factory=time.time)

    # The section that was corrected
    soap_section: str = ""  # subjective, objective, assessment, plan

    # Original AI output
    original_text: str = ""
    # Clinician-corrected version
    corrected_text: str = ""

    # Context used for generation
    transcript: str = ""
    chief_complaint: str = ""
    specialty: str = "general"
    language: str = "en"

    # Quality signal
    correction_type: str = "edit"  # edit, reject, approve, minor_fix
    severity: str = "moderate"     # minor, moderate, major

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "clinician_id": self.clinician_id,
            "clinician_role": self.clinician_role,
            "timestamp": self.timestamp,
            "soap_section": self.soap_section,
            "original_text": self.original_text,
            "corrected_text": self.corrected_text,
            "transcript": self.transcript,
            "chief_complaint": self.chief_complaint,
            "specialty": self.specialty,
            "language": self.language,
            "correction_type": self.correction_type,
            "severity": self.severity,
        }


class FeedbackCollector:
    """Collects and stores clinician feedback for LoRA training."""

    def __init__(self, feedback_dir: str = _FEEDBACK_DIR):
        self._dir = Path(feedback_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._buffer: List[ClinicalFeedback] = []
        self._buffer_limit = 50

    def record_feedback(self, feedback: ClinicalFeedback) -> None:
        """Record a clinician correction."""
        self._buffer.append(feedback)
        logger.info(
            f"Feedback recorded: session={feedback.session_id}, "
            f"section={feedback.soap_section}, "
            f"type={feedback.correction_type}"
        )
        if len(self._buffer) >= self._buffer_limit:
            self.flush()

    def flush(self) -> int:
        """Flush buffered feedback to disk."""
        if not self._buffer:
            return 0

        filename = f"feedback_{int(time.time())}.jsonl"
        path = self._dir / filename

        with open(path, "a", encoding="utf-8") as f:
            for fb in self._buffer:
                f.write(json.dumps(fb.to_dict()) + "\n")

        count = len(self._buffer)
        self._buffer.clear()
        logger.info(f"Flushed {count} feedback entries to {path}")
        return count

    def get_all_feedback(self) -> List[ClinicalFeedback]:
        """Load all feedback from disk."""
        entries = []

        for path in sorted(self._dir.glob("feedback_*.jsonl")):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        entries.append(ClinicalFeedback(**{
                            k: v for k, v in d.items()
                            if k in ClinicalFeedback.__dataclass_fields__
                        }))

        return entries

    def get_feedback_stats(self) -> Dict[str, Any]:
        """Get statistics about collected feedback."""
        entries = self.get_all_feedback()
        if not entries:
            return {"total": 0}

        sections = {}
        types = {}
        severities = {}
        for e in entries:
            sections[e.soap_section] = sections.get(e.soap_section, 0) + 1
            types[e.correction_type] = types.get(e.correction_type, 0) + 1
            severities[e.severity] = severities.get(e.severity, 0) + 1

        return {
            "total": len(entries),
            "by_section": sections,
            "by_type": types,
            "by_severity": severities,
            "pending_in_buffer": len(self._buffer),
        }


# Singleton
_collector: Optional[FeedbackCollector] = None


def get_feedback_collector() -> FeedbackCollector:
    global _collector
    if _collector is None:
        _collector = FeedbackCollector()
    return _collector
