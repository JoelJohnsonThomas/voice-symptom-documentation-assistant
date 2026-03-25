"""
NER-Based PHI Detection using Microsoft Presidio

Extends the existing regex-based PHI detection in compliance.py with
ML-powered Named Entity Recognition for detecting:
- Patient names (not detectable by regex alone)
- Addresses and geographic locations
- Ages over 89 (HIPAA Safe Harbor)
- Contextual identifiers that regex patterns miss

Architecture:
    Presidio (primary, ML-based) -> regex fallback (existing patterns)

The detector is loaded lazily to avoid startup overhead when not needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Presidio entity types mapped to HIPAA Safe Harbor categories
_HIPAA_ENTITY_TYPES = [
    "PERSON",           # Names
    "PHONE_NUMBER",     # Phone numbers
    "EMAIL_ADDRESS",    # Email addresses
    "US_SSN",           # Social Security Numbers
    "LOCATION",         # Addresses, geographic locations
    "DATE_TIME",        # Dates (DOB, admission, discharge)
    "IP_ADDRESS",       # IP addresses
    "US_DRIVER_LICENSE", # Driver's license
    "MEDICAL_LICENSE",  # Medical license numbers
    "URL",              # URLs that may contain PHI
    "NRP",              # Nationality/religious/political group
    "AGE",              # Ages (>89 are identifiers under Safe Harbor)
]

# Minimum confidence score for a detection to be included
_MIN_CONFIDENCE = 0.4


@dataclass
class PHIDetection:
    """A single PHI detection result."""
    entity_type: str
    start: int
    end: int
    score: float
    text_snippet: str  # First 4 chars + *** for audit logging


@dataclass
class PHIScanResult:
    """Result of a comprehensive PHI scan."""
    detections: list[PHIDetection] = field(default_factory=list)
    is_clean: bool = True
    detection_count: int = 0
    entity_types_found: list[str] = field(default_factory=list)
    method: str = "regex"  # "presidio", "regex", or "hybrid"

    @property
    def phi_count(self) -> int:
        return self.detection_count


class PHIDetector:
    """PHI detection service combining Presidio NER with regex fallback.

    Usage:
        detector = get_phi_detector()
        result = detector.scan("Patient John Smith, DOB 01/15/1985")
        redacted = detector.redact("Patient John Smith, DOB 01/15/1985")
    """

    def __init__(self):
        self._analyzer = None
        self._anonymizer = None
        self._presidio_available = False
        self._initialized = False

    def _init_presidio(self) -> bool:
        """Lazily initialize Presidio analyzer and anonymizer."""
        if self._initialized:
            return self._presidio_available

        self._initialized = True

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._presidio_available = True
            logger.info("Presidio PHI detector initialized successfully")
        except ImportError:
            logger.warning(
                "presidio-analyzer not installed. Falling back to regex-only PHI detection. "
                "Install with: pip install presidio-analyzer presidio-anonymizer"
            )
            self._presidio_available = False
        except Exception as e:
            logger.warning(f"Presidio initialization failed: {e}. Using regex fallback.")
            self._presidio_available = False

        return self._presidio_available

    def scan(self, text: str) -> PHIScanResult:
        """Scan text for PHI using Presidio (primary) + regex (fallback).

        Args:
            text: Text to scan for PHI.

        Returns:
            PHIScanResult with all detections.
        """
        if not text:
            return PHIScanResult()

        detections: list[PHIDetection] = []
        method = "regex"

        # Try Presidio first
        if self._init_presidio() and self._analyzer is not None:
            method = "presidio"
            try:
                results = self._analyzer.analyze(
                    text=text,
                    entities=_HIPAA_ENTITY_TYPES,
                    language="en",
                    score_threshold=_MIN_CONFIDENCE,
                )
                for r in results:
                    snippet = text[r.start:r.start + 4] + "***" if r.end - r.start > 4 else "***"
                    detections.append(PHIDetection(
                        entity_type=r.entity_type,
                        start=r.start,
                        end=r.end,
                        score=r.score,
                        text_snippet=snippet,
                    ))
            except Exception as e:
                logger.warning(f"Presidio scan failed, falling back to regex: {e}")
                method = "regex"

        # Always run regex as fallback/supplement
        from app.compliance import detect_phi as regex_detect_phi
        regex_detections = regex_detect_phi(text)
        if regex_detections:
            if method == "presidio":
                method = "hybrid"
            # Merge regex detections, avoiding duplicates (overlapping ranges)
            presidio_ranges = {(d.start, d.end) for d in detections}
            for rd in regex_detections:
                rd_range = (rd["start"], rd["end"])
                # Check for overlap with existing detections
                overlaps = any(
                    not (rd_range[1] <= p[0] or rd_range[0] >= p[1])
                    for p in presidio_ranges
                )
                if not overlaps:
                    detections.append(PHIDetection(
                        entity_type=rd["pattern_type"],
                        start=rd["start"],
                        end=rd["end"],
                        score=1.0,  # Regex matches are binary
                        text_snippet=rd["match"],
                    ))

        entity_types = list({d.entity_type for d in detections})

        return PHIScanResult(
            detections=detections,
            is_clean=len(detections) == 0,
            detection_count=len(detections),
            entity_types_found=entity_types,
            method=method,
        )

    def redact(self, text: str) -> str:
        """Redact all detected PHI from text.

        Uses Presidio anonymizer if available, otherwise falls back to
        the existing regex-based redaction in compliance.py.

        Args:
            text: Text containing potential PHI.

        Returns:
            Text with PHI replaced by redaction markers.
        """
        if not text:
            return text

        # Try Presidio anonymizer first
        if self._init_presidio() and self._analyzer is not None and self._anonymizer is not None:
            try:
                results = self._analyzer.analyze(
                    text=text,
                    entities=_HIPAA_ENTITY_TYPES,
                    language="en",
                    score_threshold=_MIN_CONFIDENCE,
                )
                if results:
                    anonymized = self._anonymizer.anonymize(text=text, analyzer_results=results)
                    redacted = anonymized.text
                else:
                    redacted = text

                # Second pass with regex for anything Presidio missed
                from app.compliance import redact_phi_text
                redacted = redact_phi_text(redacted)
                return redacted
            except Exception as e:
                logger.warning(f"Presidio redaction failed, using regex: {e}")

        # Regex-only fallback
        from app.compliance import redact_phi_text
        return redact_phi_text(text)

    def redact_for_storage(self, text: str) -> tuple[str, PHIScanResult]:
        """Redact PHI and return both the clean text and a scan report.

        Suitable for use before storing text in databases or vector stores.
        Performs double-pass redaction for safety.

        Args:
            text: Text to redact.

        Returns:
            Tuple of (redacted_text, scan_result).
        """
        redacted = self.redact(text)
        # Verify the redacted text is clean
        verification = self.scan(redacted)
        if not verification.is_clean:
            # Second pass
            redacted = self.redact(redacted)
            verification = self.scan(redacted)
        return redacted, verification


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_detector: Optional[PHIDetector] = None


def get_phi_detector() -> PHIDetector:
    """Get or create the singleton PHI detector instance."""
    global _detector
    if _detector is None:
        _detector = PHIDetector()
    return _detector
