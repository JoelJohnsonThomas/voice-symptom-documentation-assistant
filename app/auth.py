"""Authentication stub — authentication is fully removed.

All endpoints are open. A SystemPrincipal is provided for audit-log
compatibility so existing code that reads `current_user.username` etc.
continues to work without changes.
"""

from __future__ import annotations

from datetime import datetime, timezone


class SystemPrincipal:
    """Fixed principal used for audit logging when auth is disabled."""

    id = "system"
    username = "system"
    full_name = "System (No Auth)"
    role = "admin"
    is_active = True
    created_at = datetime.now(timezone.utc)


# Singleton used everywhere a "current user" is needed.
SYSTEM_USER = SystemPrincipal()
