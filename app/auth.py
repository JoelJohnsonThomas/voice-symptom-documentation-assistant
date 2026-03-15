"""Authentication stub — authentication is fully removed.

All endpoints are open. A SystemPrincipal is provided for audit-log
compatibility so existing code that reads `current_user.username` etc.
continues to work without changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    PROVIDER = "provider"
    INTAKE = "intake"
    VIEWER = "viewer"


# Role sets for endpoint access control
ALL_ROLES = list(UserRole)
INTAKE_AND_UP_ROLES = [UserRole.ADMIN, UserRole.PROVIDER, UserRole.INTAKE]


class SystemPrincipal:
    """Fixed principal used for audit logging when auth is disabled."""

    id = "system"
    username = "system"
    full_name = "System (No Auth)"
    role = UserRole.ADMIN
    is_active = True
    created_at = datetime.now(timezone.utc)


# Singleton used everywhere a "current user" is needed.
SYSTEM_USER = SystemPrincipal()


def require_roles(*roles: UserRole):
    """Stub dependency — always returns SYSTEM_USER regardless of roles."""

    async def _dep():
        return SYSTEM_USER

    return _dep
