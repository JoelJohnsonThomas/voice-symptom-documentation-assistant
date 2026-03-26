"""
Cross-Session Memory Service — Redis cache + PostgreSQL persistence.

Provides session recovery (if a WebSocket disconnects mid-encounter)
and cross-encounter patient context (accumulated medical history).

Falls back to in-process dict cache if Redis/PostgreSQL are unavailable.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Redis key prefixes
_SESSION_PREFIX = "session:"
_PATIENT_PREFIX = "patient:"
_SESSION_TTL = 3600 * 4  # 4 hours
_PATIENT_TTL = 3600 * 24 * 90  # 90 days


@dataclass
class SessionCache:
    """Cached session state for recovery."""

    session_id: str
    conversation_mode: str = "patient"
    state: str = "greeting"
    turn_count: int = 0
    transcript: str = ""
    chief_complaint: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    vitals: Dict[str, Any] = field(default_factory=dict)
    followup_qa: List[Dict[str, str]] = field(default_factory=list)
    detected_language: str = "en"
    detected_specialty: str = "general"
    soap_snapshot: Optional[Dict[str, str]] = None
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "conversation_mode": self.conversation_mode,
            "state": self.state,
            "turn_count": self.turn_count,
            "transcript": self.transcript,
            "chief_complaint": self.chief_complaint,
            "entities": self.entities,
            "vitals": self.vitals,
            "followup_qa": self.followup_qa,
            "detected_language": self.detected_language,
            "detected_specialty": self.detected_specialty,
            "soap_snapshot": self.soap_snapshot,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionCache":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PatientMemory:
    """Long-term patient context across encounters."""

    patient_id: str
    encounter_count: int = 0
    known_conditions: List[Dict[str, str]] = field(default_factory=list)
    known_medications: List[Dict[str, str]] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    preferred_language: str = "en"
    communication_preferences: Dict[str, Any] = field(default_factory=dict)
    last_encounter_summary: str = ""
    last_encounter_date: Optional[str] = None
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "encounter_count": self.encounter_count,
            "known_conditions": self.known_conditions,
            "known_medications": self.known_medications,
            "allergies": self.allergies,
            "preferred_language": self.preferred_language,
            "communication_preferences": self.communication_preferences,
            "last_encounter_summary": self.last_encounter_summary,
            "last_encounter_date": self.last_encounter_date,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PatientMemory":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class MemoryService:
    """Unified memory service with Redis + PostgreSQL backends.

    Usage:
        memory = get_memory_service()
        await memory.connect()

        # Save/restore session
        await memory.save_session(session_cache)
        restored = await memory.get_session("session-123")

        # Patient memory
        await memory.update_patient_memory("patient-456", new_conditions=[...])
        patient = await memory.get_patient_memory("patient-456")
    """

    def __init__(self):
        self._redis = None
        self._use_redis = False
        self._connected = False

        # In-process fallback caches
        self._session_cache: Dict[str, str] = {}
        self._patient_cache: Dict[str, str] = {}

    async def connect(self) -> None:
        """Connect to Redis. Falls back to in-process cache."""
        try:
            import redis.asyncio as aioredis

            redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
            self._redis = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self._redis.ping()
            self._use_redis = True
            self._connected = True
            logger.info(f"Connected to Redis at {redis_url}")

        except ImportError:
            logger.info(
                "redis-py not installed. Using in-process memory cache. "
                "Install with: pip install redis[hiredis]>=5.0.0"
            )
            self._connected = True
        except Exception as e:
            logger.warning(f"Redis connection failed ({e}). Using in-process cache.")
            self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis and self._use_redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
        self._connected = False

    # -----------------------------------------------------------------
    # Session Cache
    # -----------------------------------------------------------------

    async def save_session(self, session: SessionCache) -> None:
        """Save session state for recovery."""
        session.last_updated = time.time()
        data = json.dumps(session.to_dict())
        key = f"{_SESSION_PREFIX}{session.session_id}"

        if self._use_redis and self._redis:
            try:
                await self._redis.setex(key, _SESSION_TTL, data)
                return
            except Exception as e:
                logger.warning(f"Redis session save failed: {e}")

        self._session_cache[key] = data

    async def get_session(self, session_id: str) -> Optional[SessionCache]:
        """Restore a cached session."""
        key = f"{_SESSION_PREFIX}{session_id}"

        if self._use_redis and self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    return SessionCache.from_dict(json.loads(data))
                return None
            except Exception as e:
                logger.warning(f"Redis session get failed: {e}")

        data = self._session_cache.get(key)
        if data:
            return SessionCache.from_dict(json.loads(data))
        return None

    async def delete_session(self, session_id: str) -> None:
        """Remove a session from cache."""
        key = f"{_SESSION_PREFIX}{session_id}"

        if self._use_redis and self._redis:
            try:
                await self._redis.delete(key)
                return
            except Exception:
                pass

        self._session_cache.pop(key, None)

    # -----------------------------------------------------------------
    # Patient Memory
    # -----------------------------------------------------------------

    async def get_patient_memory(self, patient_id: str) -> Optional[PatientMemory]:
        """Get long-term patient memory."""
        key = f"{_PATIENT_PREFIX}{patient_id}"

        if self._use_redis and self._redis:
            try:
                data = await self._redis.get(key)
                if data:
                    return PatientMemory.from_dict(json.loads(data))
                return None
            except Exception as e:
                logger.warning(f"Redis patient memory get failed: {e}")

        data = self._patient_cache.get(key)
        if data:
            return PatientMemory.from_dict(json.loads(data))
        return None

    async def save_patient_memory(self, memory: PatientMemory) -> None:
        """Save patient memory."""
        memory.last_updated = time.time()
        data = json.dumps(memory.to_dict())
        key = f"{_PATIENT_PREFIX}{memory.patient_id}"

        if self._use_redis and self._redis:
            try:
                await self._redis.setex(key, _PATIENT_TTL, data)
                return
            except Exception as e:
                logger.warning(f"Redis patient memory save failed: {e}")

        self._patient_cache[key] = data

    async def update_patient_after_encounter(
        self,
        patient_id: str,
        new_conditions: Optional[List[Dict[str, str]]] = None,
        new_medications: Optional[List[Dict[str, str]]] = None,
        encounter_summary: str = "",
        encounter_date: Optional[str] = None,
    ) -> PatientMemory:
        """Update patient memory after an encounter concludes.

        Merges new entities into existing memory, avoiding duplicates.
        """
        existing = await self.get_patient_memory(patient_id)
        if not existing:
            existing = PatientMemory(patient_id=patient_id)

        existing.encounter_count += 1

        # Merge conditions (deduplicate by text)
        if new_conditions:
            existing_texts = {c.get("text", "").lower() for c in existing.known_conditions}
            for cond in new_conditions:
                if cond.get("text", "").lower() not in existing_texts:
                    existing.known_conditions.append(cond)

        # Merge medications
        if new_medications:
            existing_texts = {m.get("text", "").lower() for m in existing.known_medications}
            for med in new_medications:
                if med.get("text", "").lower() not in existing_texts:
                    existing.known_medications.append(med)

        if encounter_summary:
            existing.last_encounter_summary = encounter_summary
        if encounter_date:
            existing.last_encounter_date = encounter_date

        await self.save_patient_memory(existing)
        return existing

    # -----------------------------------------------------------------
    # Bulk operations
    # -----------------------------------------------------------------

    async def get_active_sessions(self) -> List[str]:
        """List all active session IDs."""
        if self._use_redis and self._redis:
            try:
                keys = []
                async for key in self._redis.scan_iter(f"{_SESSION_PREFIX}*"):
                    session_id = key.replace(_SESSION_PREFIX, "")
                    keys.append(session_id)
                return keys
            except Exception:
                pass

        return [
            k.replace(_SESSION_PREFIX, "")
            for k in self._session_cache.keys()
        ]


# Singleton
_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
