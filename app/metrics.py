"""
Prometheus Metrics & Model Performance Monitoring

Provides:
- Prometheus-compatible metrics for inference latency, request rates, error rates
- Model performance tracking with degradation detection
- Health dashboard data aggregation
- Alert evaluation for high error rates or latency spikes
"""

import time
import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# =====================================================
# METRIC TYPES
# =====================================================

class Counter:
    """Thread-safe monotonically increasing counter."""

    def __init__(self, name: str, description: str, label_names: tuple = ()):
        self.name = name
        self.description = description
        self.label_names = label_names
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels):
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] += amount

    def get(self, **labels) -> float:
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> list[dict]:
        with self._lock:
            return [
                {"labels": dict(zip(self.label_names, k)), "value": v}
                for k, v in self._values.items()
            ]


class Histogram:
    """Tracks value distributions with configurable buckets."""

    DEFAULT_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf"))

    def __init__(self, name: str, description: str, label_names: tuple = (),
                 buckets: tuple = None):
        self.name = name
        self.description = description
        self.label_names = label_names
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts: dict[tuple, list[int]] = defaultdict(lambda: [0] * len(self.buckets))
        self._sums: dict[tuple, float] = defaultdict(float)
        self._totals: dict[tuple, int] = defaultdict(int)
        self._recent: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=200))
        self._lock = threading.Lock()

    def observe(self, value: float, **labels):
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._sums[key] += value
            self._totals[key] += 1
            self._recent[key].append((time.time(), value))
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._counts[key][i] += 1

    def get_summary(self, **labels) -> dict:
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            total = self._totals.get(key, 0)
            if total == 0:
                return {"count": 0, "sum": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
            values = sorted(v for _, v in self._recent.get(key, []))
            n = len(values)
            return {
                "count": total,
                "sum": round(self._sums.get(key, 0), 3),
                "avg": round(self._sums.get(key, 0) / total, 3),
                "p50": round(values[n // 2], 3) if values else 0,
                "p95": round(values[int(n * 0.95)], 3) if n > 1 else (values[0] if values else 0),
                "p99": round(values[int(n * 0.99)], 3) if n > 1 else (values[0] if values else 0),
            }

    def get_recent_values(self, window_seconds: float = 300, **labels) -> list[float]:
        key = tuple(labels.get(l, "") for l in self.label_names)
        cutoff = time.time() - window_seconds
        with self._lock:
            return [v for t, v in self._recent.get(key, []) if t >= cutoff]

    def collect(self) -> list[dict]:
        with self._lock:
            results = []
            for key in self._totals:
                labels = dict(zip(self.label_names, key))
                results.append({
                    "labels": labels,
                    "count": self._totals[key],
                    "sum": round(self._sums[key], 3),
                    "buckets": {
                        str(b): self._counts[key][i]
                        for i, b in enumerate(self.buckets) if b != float("inf")
                    },
                })
            return results


class Gauge:
    """Tracks a value that can go up and down."""

    def __init__(self, name: str, description: str, label_names: tuple = ()):
        self.name = name
        self.description = description
        self.label_names = label_names
        self._values: dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels):
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] = value

    def inc(self, amount: float = 1.0, **labels):
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] += amount

    def dec(self, amount: float = 1.0, **labels):
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            self._values[key] -= amount

    def get(self, **labels) -> float:
        key = tuple(labels.get(l, "") for l in self.label_names)
        with self._lock:
            return self._values.get(key, 0.0)

    def collect(self) -> list[dict]:
        with self._lock:
            return [
                {"labels": dict(zip(self.label_names, k)), "value": v}
                for k, v in self._values.items()
            ]


# =====================================================
# GLOBAL METRIC INSTANCES
# =====================================================

# Request metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    label_names=("method", "endpoint", "status"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    label_names=("method", "endpoint"),
)

# Inference metrics
INFERENCE_COUNT = Counter(
    "inference_requests_total",
    "Total inference requests",
    label_names=("model", "status"),
)

INFERENCE_LATENCY = Histogram(
    "inference_duration_seconds",
    "Model inference latency in seconds",
    label_names=("model",),
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0, float("inf")),
)

INFERENCE_ERRORS = Counter(
    "inference_errors_total",
    "Total inference errors",
    label_names=("model", "error_type"),
)

# Active connections
ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Number of active connections",
    label_names=("type",),
)

ACTIVE_INFERENCES = Gauge(
    "active_inferences",
    "Number of active inference tasks",
    label_names=("model",),
)

# Model readiness
MODEL_READY = Gauge(
    "model_ready",
    "Whether a model is loaded and ready (1=ready, 0=not)",
    label_names=("model",),
)

# Application uptime
_start_time = time.time()

APP_UPTIME = Gauge(
    "app_uptime_seconds",
    "Application uptime in seconds",
)


def get_uptime() -> float:
    return time.time() - _start_time


# =====================================================
# ALERT EVALUATION
# =====================================================

@dataclass
class AlertRule:
    name: str
    description: str
    severity: str  # "warning" or "critical"
    active: bool = False
    last_triggered: Optional[float] = None
    value: Optional[float] = None


def evaluate_alerts() -> list[dict]:
    """Evaluate alert conditions and return active alerts."""
    alerts = []

    window = settings.metrics_alert_window_seconds

    # 1. High error rate per model
    for model in ("medasr", "medgemma", "medgemma_vision", "ner"):
        total = INFERENCE_COUNT.get(model=model, status="success") + \
                INFERENCE_COUNT.get(model=model, status="error")
        errors = INFERENCE_COUNT.get(model=model, status="error")
        if total >= 5:
            error_rate = errors / total
            if error_rate >= settings.metrics_error_rate_critical:
                alerts.append({
                    "name": f"{model}_high_error_rate",
                    "severity": "critical",
                    "description": f"{model} error rate is {error_rate:.0%} ({int(errors)}/{int(total)})",
                    "value": round(error_rate, 3),
                    "threshold": settings.metrics_error_rate_critical,
                })
            elif error_rate >= settings.metrics_error_rate_warning:
                alerts.append({
                    "name": f"{model}_elevated_error_rate",
                    "severity": "warning",
                    "description": f"{model} error rate is {error_rate:.0%} ({int(errors)}/{int(total)})",
                    "value": round(error_rate, 3),
                    "threshold": settings.metrics_error_rate_warning,
                })

    # 2. High inference latency
    for model in ("medasr", "medgemma", "medgemma_vision"):
        recent = INFERENCE_LATENCY.get_recent_values(window_seconds=window, model=model)
        if len(recent) >= 3:
            avg_latency = sum(recent) / len(recent)
            if avg_latency >= settings.metrics_latency_critical_seconds:
                alerts.append({
                    "name": f"{model}_high_latency",
                    "severity": "critical",
                    "description": f"{model} avg latency is {avg_latency:.1f}s (last {len(recent)} requests)",
                    "value": round(avg_latency, 2),
                    "threshold": settings.metrics_latency_critical_seconds,
                })
            elif avg_latency >= settings.metrics_latency_warning_seconds:
                alerts.append({
                    "name": f"{model}_elevated_latency",
                    "severity": "warning",
                    "description": f"{model} avg latency is {avg_latency:.1f}s (last {len(recent)} requests)",
                    "value": round(avg_latency, 2),
                    "threshold": settings.metrics_latency_warning_seconds,
                })

    # 3. Model not ready
    for model in ("medasr", "medgemma", "ner"):
        if MODEL_READY.get(model=model) == 0:
            alerts.append({
                "name": f"{model}_not_ready",
                "severity": "critical",
                "description": f"{model} model is not loaded or not ready",
                "value": 0,
                "threshold": 1,
            })

    return alerts


# =====================================================
# PROMETHEUS TEXT FORMAT EXPORT
# =====================================================

def generate_prometheus_text() -> str:
    """Generate Prometheus text exposition format."""
    lines = []

    def _write_metric(name, desc, mtype, entries):
        lines.append(f"# HELP {name} {desc}")
        lines.append(f"# TYPE {name} {mtype}")
        for entry in entries:
            label_str = ""
            if entry.get("labels"):
                pairs = [f'{k}="{v}"' for k, v in entry["labels"].items() if v]
                if pairs:
                    label_str = "{" + ",".join(pairs) + "}"
            if "value" in entry:
                lines.append(f"{name}{label_str} {entry['value']}")
            elif "count" in entry:
                lines.append(f"{name}_count{label_str} {entry['count']}")
                lines.append(f"{name}_sum{label_str} {entry['sum']}")
                for bucket_bound, bucket_count in entry.get("buckets", {}).items():
                    lines.append(f'{name}_bucket{{le="{bucket_bound}"{label_str[1:] if label_str else "}"} {bucket_count}')

    _write_metric(REQUEST_COUNT.name, REQUEST_COUNT.description, "counter", REQUEST_COUNT.collect())
    _write_metric(REQUEST_LATENCY.name, REQUEST_LATENCY.description, "histogram", REQUEST_LATENCY.collect())
    _write_metric(INFERENCE_COUNT.name, INFERENCE_COUNT.description, "counter", INFERENCE_COUNT.collect())
    _write_metric(INFERENCE_LATENCY.name, INFERENCE_LATENCY.description, "histogram", INFERENCE_LATENCY.collect())
    _write_metric(INFERENCE_ERRORS.name, INFERENCE_ERRORS.description, "counter", INFERENCE_ERRORS.collect())
    _write_metric(ACTIVE_CONNECTIONS.name, ACTIVE_CONNECTIONS.description, "gauge", ACTIVE_CONNECTIONS.collect())
    _write_metric(ACTIVE_INFERENCES.name, ACTIVE_INFERENCES.description, "gauge", ACTIVE_INFERENCES.collect())
    _write_metric(MODEL_READY.name, MODEL_READY.description, "gauge", MODEL_READY.collect())

    # Uptime
    APP_UPTIME.set(get_uptime())
    _write_metric(APP_UPTIME.name, APP_UPTIME.description, "gauge", APP_UPTIME.collect())

    lines.append("")
    return "\n".join(lines)


# =====================================================
# DASHBOARD DATA
# =====================================================

def get_dashboard_data() -> dict:
    """Aggregate all metrics for the monitoring dashboard."""
    models = ("medasr", "medgemma", "medgemma_vision", "ner")

    model_stats = {}
    for model in models:
        summary = INFERENCE_LATENCY.get_summary(model=model)
        success = INFERENCE_COUNT.get(model=model, status="success")
        errors = INFERENCE_COUNT.get(model=model, status="error")
        total = success + errors
        model_stats[model] = {
            "total_requests": int(total),
            "success": int(success),
            "errors": int(errors),
            "error_rate": round(errors / total, 3) if total > 0 else 0,
            "latency": summary,
            "ready": MODEL_READY.get(model=model) == 1,
        }

    return {
        "uptime_seconds": round(get_uptime(), 1),
        "models": model_stats,
        "active_http_connections": ACTIVE_CONNECTIONS.get(type="http"),
        "active_websockets": ACTIVE_CONNECTIONS.get(type="websocket"),
        "alerts": evaluate_alerts(),
    }
