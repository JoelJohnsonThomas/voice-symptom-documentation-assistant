"""Session analytics and clinician feedback service.

Phase 9: Provides:
- Session analytics (chief complaints, durations, SOAP quality)
- Clinician feedback collection (thumbs up/down per SOAP field)
- SIEM-compatible audit log export (CEF / JSON Lines)
- Alerting integration helpers (PagerDuty, Slack webhook)
"""

import json
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# =====================================================
# Session Analytics
# =====================================================

class SessionAnalytics:
    """Aggregates session-level statistics for dashboards."""

    def __init__(self):
        self._chief_complaints: Counter = Counter()
        self._durations: List[float] = []
        self._soap_scores: List[float] = []
        self._sessions_by_hour: Counter = Counter()
        self._language_counts: Counter = Counter()
        self._specialty_counts: Counter = Counter()

    def record_session(
        self,
        chief_complaint: str = "",
        duration_seconds: float = 0.0,
        soap_quality_score: float = 0.0,
        language: str = "en",
        specialty: str = "general",
    ) -> None:
        if chief_complaint:
            # Normalize to lowercase, truncate
            normalized = chief_complaint.lower().strip()[:100]
            self._chief_complaints[normalized] += 1
        if duration_seconds > 0:
            self._durations.append(duration_seconds)
        if soap_quality_score > 0:
            self._soap_scores.append(soap_quality_score)
        self._sessions_by_hour[datetime.now().hour] += 1
        self._language_counts[language] += 1
        self._specialty_counts[specialty] += 1

    def get_summary(self, top_n: int = 10) -> Dict[str, Any]:
        total = sum(self._chief_complaints.values())
        avg_duration = (
            sum(self._durations) / len(self._durations) if self._durations else 0
        )
        avg_soap = (
            sum(self._soap_scores) / len(self._soap_scores) if self._soap_scores else 0
        )

        return {
            "total_sessions": total,
            "top_chief_complaints": self._chief_complaints.most_common(top_n),
            "avg_session_duration_seconds": round(avg_duration, 1),
            "avg_soap_quality_score": round(avg_soap, 3),
            "sessions_by_hour": dict(self._sessions_by_hour),
            "language_distribution": dict(self._language_counts),
            "specialty_distribution": dict(self._specialty_counts),
            "total_durations_recorded": len(self._durations),
            "total_soap_scores_recorded": len(self._soap_scores),
        }


# =====================================================
# Clinician Feedback
# =====================================================

@dataclass
class SOAPFeedback:
    session_id: str
    field: str          # "subjective", "objective", "assessment", "plan"
    rating: int         # 1 = thumbs up, -1 = thumbs down
    comment: str = ""
    provider_id: str = ""
    timestamp: float = field(default_factory=time.time)


class FeedbackCollector:
    """Collects and aggregates clinician feedback on SOAP quality."""

    def __init__(self):
        self._feedback: List[SOAPFeedback] = []
        self._field_ratings: Dict[str, List[int]] = defaultdict(list)

    def submit(self, feedback: SOAPFeedback) -> None:
        self._feedback.append(feedback)
        self._field_ratings[feedback.field].append(feedback.rating)
        logger.info(
            "Feedback recorded: session=%s field=%s rating=%d",
            feedback.session_id, feedback.field, feedback.rating,
        )

    def get_field_scores(self) -> Dict[str, Dict[str, Any]]:
        """Aggregate satisfaction per SOAP field."""
        result = {}
        for fld in ["subjective", "objective", "assessment", "plan"]:
            ratings = self._field_ratings.get(fld, [])
            if not ratings:
                result[fld] = {"total": 0, "positive_pct": 0.0}
                continue
            positives = sum(1 for r in ratings if r > 0)
            result[fld] = {
                "total": len(ratings),
                "positive_pct": round(positives / len(ratings) * 100, 1),
            }
        return result

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [
            {
                "session_id": f.session_id,
                "field": f.field,
                "rating": f.rating,
                "comment": f.comment,
                "timestamp": f.timestamp,
            }
            for f in self._feedback[-limit:]
        ]


# =====================================================
# SIEM Audit Export (CEF / JSON Lines)
# =====================================================

def format_cef(
    event_type: str,
    severity: int,
    details: Dict[str, Any],
    device_vendor: str = "VoxDoc",
    device_product: str = "VoiceIntake",
    device_version: str = "1.0",
) -> str:
    """Format an audit event as a CEF (Common Event Format) string.

    CEF:Version|Device Vendor|Device Product|Device Version|Event ID|Name|Severity|Extensions
    """
    extensions = " ".join(f"{k}={v}" for k, v in details.items() if v is not None)
    return (
        f"CEF:0|{device_vendor}|{device_product}|{device_version}"
        f"|{event_type}|{event_type}|{severity}|{extensions}"
    )


def format_jsonlines(event_type: str, details: Dict[str, Any]) -> str:
    """Format an audit event as a JSON Lines entry."""
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        **details,
    }
    return json.dumps(record, default=str)


def export_audit_logs(
    logs: List[Dict[str, Any]],
    fmt: str = "jsonlines",
) -> str:
    """Export audit log entries in the specified format.

    Args:
        logs: List of audit log dicts (from DB query).
        fmt: "jsonlines" or "cef".

    Returns:
        Formatted string with one entry per line.
    """
    lines = []
    for log in logs:
        event = log.get("action", "unknown")
        details = {
            "user": log.get("username", ""),
            "ip": log.get("ip_address", ""),
            "resource": log.get("resource", ""),
            "session_id": log.get("session_id", ""),
        }
        if fmt == "cef":
            lines.append(format_cef(event, 3, details))
        else:
            lines.append(format_jsonlines(event, details))
    return "\n".join(lines)


# =====================================================
# Alerting Integrations
# =====================================================

async def send_slack_alert(
    webhook_url: str,
    title: str,
    message: str,
    severity: str = "warning",
) -> bool:
    """Send an alert to a Slack webhook."""
    color_map = {"info": "#36a64f", "warning": "#ff9900", "critical": "#ff0000"}
    payload = {
        "attachments": [
            {
                "color": color_map.get(severity, "#ff9900"),
                "title": f"VoxDoc Alert: {title}",
                "text": message,
                "ts": int(time.time()),
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error("Slack alert failed: %s", e)
        return False


async def send_pagerduty_event(
    routing_key: str,
    summary: str,
    severity: str = "warning",
    source: str = "voxdoc",
) -> bool:
    """Send a PagerDuty Events API v2 trigger."""
    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "payload": {
            "summary": summary,
            "severity": severity,
            "source": source,
            "component": "voice-intake",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://events.pagerduty.com/v2/enqueue", json=payload
            )
            return resp.status_code == 202
    except Exception as e:
        logger.error("PagerDuty event failed: %s", e)
        return False


# =====================================================
# Grafana Dashboard JSON Generator
# =====================================================

def generate_grafana_dashboard() -> Dict[str, Any]:
    """Generate a Grafana dashboard JSON for VoxDoc metrics.

    Import this JSON into Grafana with a Prometheus data source.
    """
    return {
        "dashboard": {
            "title": "VoxDoc - Voice Intake Monitoring",
            "uid": "voxdoc-main",
            "timezone": "browser",
            "refresh": "30s",
            "panels": [
                {
                    "title": "Request Rate (rpm)",
                    "type": "timeseries",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                    "targets": [{"expr": "rate(voxdoc_requests_total[5m]) * 60"}],
                },
                {
                    "title": "Inference Latency (p95)",
                    "type": "timeseries",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                    "targets": [
                        {"expr": "histogram_quantile(0.95, rate(voxdoc_inference_latency_bucket[5m]))"}
                    ],
                },
                {
                    "title": "Error Rate",
                    "type": "stat",
                    "gridPos": {"h": 4, "w": 6, "x": 0, "y": 8},
                    "targets": [
                        {
                            "expr": 'rate(voxdoc_requests_total{status="error"}[5m]) / rate(voxdoc_requests_total[5m])'
                        }
                    ],
                },
                {
                    "title": "Active Connections",
                    "type": "gauge",
                    "gridPos": {"h": 4, "w": 6, "x": 6, "y": 8},
                    "targets": [{"expr": "voxdoc_active_connections"}],
                },
                {
                    "title": "Model Readiness",
                    "type": "stat",
                    "gridPos": {"h": 4, "w": 6, "x": 12, "y": 8},
                    "targets": [{"expr": "voxdoc_model_ready"}],
                },
                {
                    "title": "GPU Memory Usage",
                    "type": "gauge",
                    "gridPos": {"h": 4, "w": 6, "x": 18, "y": 8},
                    "targets": [{"expr": "voxdoc_gpu_memory_used_bytes / voxdoc_gpu_memory_total_bytes"}],
                },
                {
                    "title": "Top Chief Complaints",
                    "type": "table",
                    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 12},
                    "targets": [{"expr": "topk(10, voxdoc_chief_complaints_total)"}],
                },
                {
                    "title": "Session Duration Distribution",
                    "type": "histogram",
                    "gridPos": {"h": 8, "w": 12, "x": 12, "y": 12},
                    "targets": [{"expr": "voxdoc_session_duration_seconds_bucket"}],
                },
            ],
        },
        "overwrite": True,
    }


# =====================================================
# Singletons
# =====================================================

_analytics: Optional[SessionAnalytics] = None
_feedback: Optional[FeedbackCollector] = None


def get_session_analytics() -> SessionAnalytics:
    global _analytics
    if _analytics is None:
        _analytics = SessionAnalytics()
    return _analytics


def get_feedback_collector() -> FeedbackCollector:
    global _feedback
    if _feedback is None:
        _feedback = FeedbackCollector()
    return _feedback
