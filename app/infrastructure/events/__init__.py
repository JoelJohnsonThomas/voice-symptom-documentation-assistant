"""
NATS JetStream Event Bus Infrastructure (Phase 3)

Provides a publish/subscribe event bus for decoupled communication
between microservices and agents. Uses NATS JetStream for persistence,
at-least-once delivery, and replay capabilities.

Falls back to an in-process async event bus if NATS is unavailable.
"""

from app.infrastructure.events.event_bus import (
    EventBus,
    Event,
    EventHandler,
    get_event_bus,
    publish_event,
    subscribe,
)

__all__ = [
    "EventBus",
    "Event",
    "EventHandler",
    "get_event_bus",
    "publish_event",
    "subscribe",
]
