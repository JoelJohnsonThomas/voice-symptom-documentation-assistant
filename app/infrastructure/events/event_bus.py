"""
Event Bus — NATS JetStream with in-process fallback.

Subjects follow a hierarchical naming convention:
    clinical.{event_type}.{session_id}

Event types:
    - clinical.transcription.completed
    - clinical.entities.extracted
    - clinical.documentation.generated
    - clinical.documentation.updated
    - clinical.safety.emergency
    - clinical.safety.phi_detected
    - clinical.compliance.fhir_exported
    - clinical.compliance.audit_logged
    - clinical.session.started
    - clinical.session.ended
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Type alias for event handler functions
EventHandler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    """A structured event for the event bus."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subject: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    source: str = ""  # Originating service/agent

    def to_json(self) -> bytes:
        return json.dumps({
            "id": self.id,
            "subject": self.subject,
            "data": self.data,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "source": self.source,
        }).encode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes) -> "Event":
        d = json.loads(raw)
        return cls(**d)


class EventBus:
    """Event bus with NATS JetStream backend and in-process fallback.

    Usage:
        bus = get_event_bus()
        await bus.connect()

        # Subscribe to events
        async def on_transcription(event: Event):
            print(f"Got transcription: {event.data}")

        await bus.subscribe("clinical.transcription.*", on_transcription)

        # Publish events
        await bus.publish(Event(
            subject="clinical.transcription.completed",
            session_id="abc-123",
            data={"transcript": "...", "language": "en"},
            source="asr_service",
        ))
    """

    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self._nats_url = nats_url
        self._nc = None  # nats.Client
        self._js = None  # JetStream context
        self._connected = False
        self._use_nats = False

        # In-process fallback
        self._local_handlers: Dict[str, List[EventHandler]] = {}
        self._event_history: List[Event] = []
        self._max_history = 1000

    async def connect(self) -> None:
        """Connect to NATS server. Falls back to in-process if unavailable."""
        try:
            import nats

            self._nc = await nats.connect(self._nats_url)
            self._js = self._nc.jetstream()

            # Ensure the clinical stream exists
            try:
                await self._js.find_stream_name_by_subject("clinical.>")
            except Exception:
                await self._js.add_stream(
                    name="CLINICAL",
                    subjects=["clinical.>"],
                    retention="limits",
                    max_msgs=100_000,
                    max_age=7 * 24 * 3600 * 10**9,  # 7 days in nanoseconds
                    storage="file",
                    discard="old",
                )
                logger.info("Created NATS JetStream stream 'CLINICAL'")

            self._connected = True
            self._use_nats = True
            logger.info(f"Connected to NATS at {self._nats_url}")

        except ImportError:
            logger.info(
                "nats-py not installed. Using in-process event bus. "
                "Install with: pip install nats-py>=2.7.0"
            )
            self._connected = True
        except Exception as e:
            logger.warning(
                f"NATS connection failed ({e}). Using in-process event bus."
            )
            self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from NATS."""
        if self._nc and self._use_nats:
            try:
                await self._nc.drain()
                await self._nc.close()
            except Exception as e:
                logger.debug(f"NATS disconnect error: {e}")
        self._connected = False
        self._use_nats = False

    async def publish(self, event: Event) -> None:
        """Publish an event to the bus."""
        if not self._connected:
            await self.connect()

        if self._use_nats and self._js:
            try:
                ack = await self._js.publish(
                    event.subject,
                    event.to_json(),
                    headers={"Nats-Msg-Id": event.id},
                )
                logger.debug(
                    f"Event published to NATS: {event.subject} "
                    f"(stream={ack.stream}, seq={ack.seq})"
                )
                return
            except Exception as e:
                logger.warning(f"NATS publish failed: {e}. Using local fallback.")

        # In-process fallback
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Dispatch to matching local handlers
        await self._dispatch_local(event)

    async def subscribe(
        self,
        subject: str,
        handler: EventHandler,
        queue_group: Optional[str] = None,
        deliver_policy: str = "new",
    ) -> None:
        """Subscribe to events matching a subject pattern.

        Args:
            subject: NATS subject pattern (supports wildcards * and >).
            handler: Async function to call for each event.
            queue_group: Queue group for load-balanced consumption.
            deliver_policy: "new", "all", or "last" for JetStream replay.
        """
        if self._use_nats and self._js:
            try:
                import nats

                deliver_map = {
                    "new": nats.js.api.DeliverPolicy.NEW,
                    "all": nats.js.api.DeliverPolicy.ALL,
                    "last": nats.js.api.DeliverPolicy.LAST,
                }

                config = nats.js.api.ConsumerConfig(
                    deliver_policy=deliver_map.get(deliver_policy, nats.js.api.DeliverPolicy.NEW),
                    ack_policy=nats.js.api.AckPolicy.EXPLICIT,
                )

                sub = await self._js.subscribe(
                    subject,
                    queue=queue_group or "",
                    config=config,
                )

                # Background task to process messages
                asyncio.create_task(
                    self._nats_message_loop(sub, handler, subject)
                )
                logger.info(f"Subscribed to NATS: {subject}")
                return
            except Exception as e:
                logger.warning(f"NATS subscribe failed: {e}. Using local fallback.")

        # In-process fallback
        self._local_handlers.setdefault(subject, []).append(handler)
        logger.info(f"Subscribed (local): {subject}")

    async def _nats_message_loop(self, sub, handler: EventHandler, subject: str) -> None:
        """Process messages from a NATS subscription."""
        try:
            async for msg in sub.messages:
                try:
                    event = Event.from_json(msg.data)
                    await handler(event)
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Error processing NATS message on {subject}: {e}")
                    await msg.nak()
        except Exception as e:
            logger.warning(f"NATS message loop ended for {subject}: {e}")

    async def _dispatch_local(self, event: Event) -> None:
        """Dispatch event to matching local handlers (wildcard support)."""
        for pattern, handlers in self._local_handlers.items():
            if self._matches_subject(pattern, event.subject):
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception as e:
                        logger.error(
                            f"Local handler error for {event.subject}: {e}"
                        )

    @staticmethod
    def _matches_subject(pattern: str, subject: str) -> bool:
        """Check if a subject matches a NATS-style pattern.

        Supports:
        - * matches a single token
        - > matches one or more tokens (must be last)
        - Exact match
        """
        pattern_parts = pattern.split(".")
        subject_parts = subject.split(".")

        for i, pp in enumerate(pattern_parts):
            if pp == ">":
                return True  # Matches rest
            if i >= len(subject_parts):
                return False
            if pp != "*" and pp != subject_parts[i]:
                return False

        return len(pattern_parts) == len(subject_parts)

    def get_event_history(
        self,
        subject_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Event]:
        """Get recent events from the in-process history."""
        events = self._event_history
        if subject_filter:
            events = [
                e for e in events
                if self._matches_subject(subject_filter, e.subject)
            ]
        return events[-limit:]


# =====================================================================
# Convenience functions
# =====================================================================

_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus singleton."""
    global _event_bus
    if _event_bus is None:
        nats_url = getattr(settings, "nats_url", "nats://localhost:4222")
        _event_bus = EventBus(nats_url=nats_url)
    return _event_bus


async def publish_event(
    subject: str,
    data: Dict[str, Any],
    session_id: Optional[str] = None,
    source: str = "",
) -> None:
    """Convenience: publish an event to the global bus."""
    bus = get_event_bus()
    event = Event(
        subject=subject,
        data=data,
        session_id=session_id,
        source=source,
    )
    await bus.publish(event)


async def subscribe(
    subject: str,
    handler: EventHandler,
    queue_group: Optional[str] = None,
) -> None:
    """Convenience: subscribe to events on the global bus."""
    bus = get_event_bus()
    await bus.subscribe(subject, handler, queue_group=queue_group)
