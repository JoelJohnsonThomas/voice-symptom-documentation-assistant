"""
OpenTelemetry Distributed Observability (Phase 4)

Replaces in-process Prometheus counters with OpenTelemetry SDK for:
- Distributed tracing across microservices (ASR → LLM → NER → API)
- Metrics export to Prometheus/Grafana/Datadog
- Structured logging with trace context correlation
- Automatic FastAPI instrumentation

Falls back to the existing app.metrics module if OTel is not installed.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level state
_tracer = None
_meter = None
_initialized = False


def init_telemetry(
    service_name: str = "voice-triage-api",
    otlp_endpoint: Optional[str] = None,
) -> bool:
    """Initialize OpenTelemetry tracing, metrics, and logging.

    Args:
        service_name: OTEL service name.
        otlp_endpoint: OTLP collector endpoint (e.g. http://otel-collector:4317).

    Returns:
        True if OTel was initialized, False if using fallback.
    """
    global _tracer, _meter, _initialized

    if _initialized:
        return _tracer is not None

    otlp_endpoint = otlp_endpoint or getattr(
        settings, "otel_endpoint", "http://localhost:4317"
    )

    try:
        from opentelemetry import trace, metrics
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        resource = Resource.create({SERVICE_NAME: service_name})

        # Tracing
        tracer_provider = TracerProvider(resource=resource)
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _tracer = trace.get_tracer(service_name)

        # Metrics
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=15000
        )
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        _meter = metrics.get_meter(service_name)

        _initialized = True
        logger.info(f"OpenTelemetry initialized: service={service_name}, endpoint={otlp_endpoint}")
        return True

    except ImportError:
        logger.info(
            "OpenTelemetry not installed. Using fallback metrics. "
            "Install with: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc "
            "opentelemetry-instrumentation-fastapi"
        )
        _initialized = True
        return False
    except Exception as e:
        logger.warning(f"OpenTelemetry initialization failed: {e}")
        _initialized = True
        return False


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI application with OpenTelemetry auto-instrumentation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI OpenTelemetry instrumentation applied")
    except ImportError:
        logger.debug("FastAPI OTel instrumentation not available")
    except Exception as e:
        logger.debug(f"FastAPI instrumentation failed: {e}")


def get_tracer(name: str = "voice-triage"):
    """Get an OpenTelemetry tracer, or a no-op fallback."""
    if _tracer:
        return _tracer
    # Return a no-op tracer
    return _NoOpTracer()


def get_meter(name: str = "voice-triage"):
    """Get an OpenTelemetry meter, or a no-op fallback."""
    if _meter:
        return _meter
    return _NoOpMeter()


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
):
    """Context manager for creating a traced span.

    Usage:
        with trace_span("generate_soap", {"specialty": "emergency"}):
            result = medgemma.generate_documentation(...)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, str(v))
        try:
            yield span
        except Exception as e:
            span.set_attribute("error", True)
            span.set_attribute("error.message", str(e))
            raise


# =====================================================================
# Clinical-Specific Metrics
# =====================================================================

class ClinicalMetrics:
    """Pre-defined metrics for clinical documentation pipeline."""

    def __init__(self):
        meter = get_meter()
        self._meter = meter
        self._initialized = _meter is not None

        if self._initialized:
            self.soap_generation_duration = meter.create_histogram(
                name="soap.generation.duration",
                description="SOAP note generation time in seconds",
                unit="s",
            )
            self.soap_generation_count = meter.create_counter(
                name="soap.generation.count",
                description="Number of SOAP notes generated",
            )
            self.asr_transcription_duration = meter.create_histogram(
                name="asr.transcription.duration",
                description="ASR transcription time in seconds",
                unit="s",
            )
            self.ner_extraction_count = meter.create_counter(
                name="ner.extraction.count",
                description="Number of NER extractions performed",
            )
            self.safety_emergency_count = meter.create_counter(
                name="safety.emergency.count",
                description="Number of emergency escalations triggered",
            )
            self.hallucination_risk_high = meter.create_counter(
                name="hallucination.risk.high",
                description="Number of high-risk hallucination detections",
            )
            self.active_sessions = meter.create_up_down_counter(
                name="sessions.active",
                description="Currently active sessions",
            )
            self.confidence_score = meter.create_histogram(
                name="soap.confidence.score",
                description="SOAP section confidence scores",
            )

    def record_soap_generated(
        self, duration: float, specialty: str = "general", mode: str = "interactive"
    ) -> None:
        if not self._initialized:
            return
        attrs = {"specialty": specialty, "mode": mode}
        self.soap_generation_duration.record(duration, attributes=attrs)
        self.soap_generation_count.add(1, attributes=attrs)

    def record_asr_transcription(self, duration: float, language: str = "en") -> None:
        if not self._initialized:
            return
        self.asr_transcription_duration.record(
            duration, attributes={"language": language}
        )

    def record_emergency(self, emergency_type: str) -> None:
        if not self._initialized:
            return
        self.safety_emergency_count.add(
            1, attributes={"type": emergency_type}
        )

    def record_hallucination_risk(self, risk_level: str, section: str) -> None:
        if not self._initialized:
            return
        if risk_level == "high":
            self.hallucination_risk_high.add(
                1, attributes={"section": section}
            )

    def session_started(self) -> None:
        if self._initialized:
            self.active_sessions.add(1)

    def session_ended(self) -> None:
        if self._initialized:
            self.active_sessions.add(-1)


# Singleton
_clinical_metrics: Optional[ClinicalMetrics] = None


def get_clinical_metrics() -> ClinicalMetrics:
    global _clinical_metrics
    if _clinical_metrics is None:
        _clinical_metrics = ClinicalMetrics()
    return _clinical_metrics


# =====================================================================
# No-op fallbacks
# =====================================================================

class _NoOpSpan:
    def set_attribute(self, key, value): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()
    start_span = start_as_current_span


class _NoOpMeter:
    def create_counter(self, **kwargs): return _NoOpCounter()
    def create_histogram(self, **kwargs): return _NoOpHistogram()
    def create_up_down_counter(self, **kwargs): return _NoOpCounter()


class _NoOpCounter:
    def add(self, value, **kwargs): pass


class _NoOpHistogram:
    def record(self, value, **kwargs): pass
