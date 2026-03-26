"""
Cross-Session Memory Service (Phase 3)

Provides persistent patient/session context that survives across
multiple encounters. Uses Redis for fast session cache and PostgreSQL
for durable long-term memory.

Memory types:
- **Session cache**: Active session state (Redis, TTL-based)
- **Patient history**: Cross-encounter summaries (PostgreSQL)
- **Entity memory**: Accumulated conditions/medications per patient
- **Preference memory**: Patient communication preferences, language
"""

from app.services.memory.memory_service import (
    MemoryService,
    get_memory_service,
    SessionCache,
    PatientMemory,
)

__all__ = [
    "MemoryService",
    "get_memory_service",
    "SessionCache",
    "PatientMemory",
]
