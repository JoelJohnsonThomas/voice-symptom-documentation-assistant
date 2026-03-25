"""Authentication and authorization module.

When ``settings.auth_enabled`` is ``False`` (default), all endpoints remain
open and the ``SYSTEM_USER`` stub is returned — identical to the previous
behaviour.  When ``True``, JWT Bearer tokens are required and RBAC is enforced.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Login rate limiting (brute-force protection)
# ---------------------------------------------------------------------------

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()
_LOGIN_WINDOW_SECONDS = 300  # 5-minute window
_LOGIN_MAX_ATTEMPTS = 5      # Max failures before lockout
_LOGIN_LOCKOUT_SECONDS = 900  # 15-minute lockout after exceeding max


def _check_login_rate_limit(identifier: str) -> None:
    """Check if a login identifier (username or IP) is rate-limited.

    Raises HTTPException 429 if too many failed attempts.
    """
    now = time.monotonic()

    with _login_lock:
        # Clean old entries
        _login_attempts[identifier] = [
            ts for ts in _login_attempts[identifier]
            if now - ts < _LOGIN_LOCKOUT_SECONDS
        ]

        recent = [
            ts for ts in _login_attempts[identifier]
            if now - ts < _LOGIN_WINDOW_SECONDS
        ]

        if len(recent) >= _LOGIN_MAX_ATTEMPTS:
            logger.warning(f"Login rate limit exceeded for: {identifier}")
            raise HTTPException(
                status_code=429,
                detail="Too many failed login attempts. Please try again later.",
                headers={"Retry-After": str(_LOGIN_LOCKOUT_SECONDS)},
            )


def _record_failed_login(identifier: str) -> None:
    """Record a failed login attempt for rate limiting."""
    with _login_lock:
        _login_attempts[identifier].append(time.monotonic())


def _clear_login_attempts(identifier: str) -> None:
    """Clear failed login attempts after successful login."""
    with _login_lock:
        _login_attempts.pop(identifier, None)


# ---------------------------------------------------------------------------
# Server-side session activity tracking
# ---------------------------------------------------------------------------

_session_last_activity: dict[str, float] = {}
_session_lock = Lock()


def _update_session_activity(user_id: str) -> None:
    """Record a user's last activity timestamp for server-side timeout."""
    with _session_lock:
        _session_last_activity[user_id] = time.monotonic()


def _check_session_timeout(user_id: str) -> None:
    """Check if a user's session has exceeded the inactivity timeout.

    Raises HTTPException 401 if the session is expired.
    """
    if settings.session_inactivity_timeout_minutes <= 0:
        return  # Timeout disabled

    with _session_lock:
        last_activity = _session_last_activity.get(user_id)

    if last_activity is None:
        # First request — initialize
        _update_session_activity(user_id)
        return

    elapsed_minutes = (time.monotonic() - last_activity) / 60
    if elapsed_minutes > settings.session_inactivity_timeout_minutes:
        logger.info(f"Session timeout for user {user_id} after {elapsed_minutes:.1f} min inactivity")
        # Clear the session
        with _session_lock:
            _session_last_activity.pop(user_id, None)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to inactivity. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update activity
    _update_session_activity(user_id)

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    ADMIN = "admin"
    PROVIDER = "provider"
    INTAKE = "intake"
    VIEWER = "viewer"


ALL_ROLES = list(UserRole)
INTAKE_AND_UP_ROLES = [UserRole.ADMIN, UserRole.PROVIDER, UserRole.INTAKE]

# ---------------------------------------------------------------------------
# System principal (used when auth is disabled)
# ---------------------------------------------------------------------------

class SystemPrincipal:
    """Fixed principal used for audit logging when auth is disabled."""
    id = "system"
    username = "system"
    full_name = "System (No Auth)"
    role = UserRole.ADMIN
    is_active = True
    created_at = datetime.now(timezone.utc)


SYSTEM_USER = SystemPrincipal()

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)

# ---------------------------------------------------------------------------
# JWT token helpers
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    role: str,
    extra_claims: Optional[dict] = None,
) -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Create a longer-lived JWT refresh token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_mfa_token(user_id: str) -> str:
    """Create a very short-lived token for MFA verification step."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "mfa_pending",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def hash_token(token: str) -> str:
    """SHA-256 hash of a refresh token for safe DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()

# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Extract and validate the current user from the Authorization header.

    When ``auth_enabled`` is ``False``, returns ``SYSTEM_USER`` immediately.
    """
    if not settings.auth_enabled:
        return SYSTEM_USER

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.db import crud
    user = await crud.get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Server-side session inactivity timeout
    _check_session_timeout(str(user.id))

    return user


# ---------------------------------------------------------------------------
# TOTP secret encryption helpers
# ---------------------------------------------------------------------------

def encrypt_totp_secret(plaintext_secret: str) -> str:
    """Encrypt a TOTP secret before storing in the database.

    Uses the application's encryption module (AES-256-GCM) when
    encryption at rest is enabled. Otherwise returns the secret as-is.
    """
    try:
        from app.encryption import encrypt_data
        return encrypt_data(plaintext_secret)
    except Exception:
        return plaintext_secret


def decrypt_totp_secret(stored_secret: str) -> str:
    """Decrypt a TOTP secret retrieved from the database."""
    try:
        from app.encryption import decrypt_data
        return decrypt_data(stored_secret)
    except Exception:
        return stored_secret


def require_roles(*roles: UserRole):
    """Return a FastAPI dependency that enforces role-based access.

    When ``auth_enabled`` is ``False``, returns ``SYSTEM_USER`` (stub behaviour).
    """
    async def _dep(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        if not settings.auth_enabled:
            return SYSTEM_USER

        user = await get_current_user(request, db)
        if UserRole(user.role) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' not authorized. Required: {[r.value for r in roles]}",
            )
        return user

    return _dep
