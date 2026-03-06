"""
Structured Logging with Correlation IDs

Provides:
- JSON-formatted structured log output
- Per-request correlation ID injection via contextvars
- Request/response logging with timing and metadata
"""

import logging
import json
import uuid
import time
from contextvars import ContextVar
from typing import Optional

from app.config import settings

# Context variable for correlation ID — propagated across async tasks automatically
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str:
    """Get the current correlation ID, or generate a new one."""
    cid = correlation_id_var.get()
    if cid is None:
        cid = str(uuid.uuid4())
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str):
    """Set a specific correlation ID for the current context."""
    correlation_id_var.set(cid)


class StructuredJsonFormatter(logging.Formatter):
    """Outputs log records as single-line JSON with correlation ID."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        # Add extra fields if present
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "status_code"):
            log_entry["status_code"] = record.status_code
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "model"):
            log_entry["model"] = record.model
        if hasattr(record, "user"):
            log_entry["user"] = record.user
        if hasattr(record, "client_ip"):
            log_entry["client_ip"] = record.client_ip

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


class CorrelationIdFilter(logging.Filter):
    """Injects correlation_id into every log record for non-JSON formatters."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        return True


def configure_logging():
    """Set up structured logging based on settings."""
    root_logger = logging.getLogger()

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    handler = logging.StreamHandler()

    if settings.structured_logging_enabled:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(correlation_id)s] %(message)s"
        ))
        handler.addFilter(CorrelationIdFilter())

    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
