"""Authentication, JWT, and RBAC helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud
from app.db.database import get_db


class UserRole(str, Enum):
    ADMIN = "admin"
    CLINICIAN = "clinician"
    INTAKE_STAFF = "intake_staff"


ROLE_ALIASES = {
    "admin": UserRole.ADMIN.value,
    "clinician": UserRole.CLINICIAN.value,
    "intake_staff": UserRole.INTAKE_STAFF.value,
    "intake-staff": UserRole.INTAKE_STAFF.value,
    "intake staff": UserRole.INTAKE_STAFF.value,
}


class SystemPrincipal:
    """Fallback principal used when auth is disabled."""

    id = "system"
    username = "system"
    full_name = "System (Auth Disabled)"
    role = UserRole.ADMIN.value
    is_active = True
    created_at = datetime.now(timezone.utc)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def normalize_role(value: str) -> str:
    normalized = ROLE_ALIASES.get((value or "").strip().lower())
    if not normalized:
        raise ValueError(
            "Invalid role. Allowed roles: admin, clinician, intake_staff."
        )
    return normalized


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    salt = secrets.token_bytes(16)
    iterations = settings.password_hash_iterations
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{_base64url_encode(salt)}${_base64url_encode(digest)}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against PBKDF2-SHA256 hash format."""
    try:
        scheme, iterations_str, salt_b64, expected_b64 = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        salt = _base64url_decode(salt_b64)
        expected = _base64url_decode(expected_b64)
        current = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(current, expected)
    except Exception:
        return False


def create_access_token(*, username: str, role: str) -> str:
    """Create an HS256 JWT access token."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": username,
        "role": normalize_role(role),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_base64url_encode(_json_bytes(header))}."
        f"{_base64url_encode(_json_bytes(payload))}"
    )
    signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    """Validate and decode an HS256 JWT access token."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError as exc:
        raise _credentials_exception() from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected_signature = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided_signature = _base64url_decode(signature_b64)
    except Exception as exc:
        raise _credentials_exception("Invalid token signature.") from exc
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise _credentials_exception("Invalid token signature.")

    try:
        payload = json.loads(_base64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise _credentials_exception("Invalid token payload.") from exc

    exp = payload.get("exp")
    sub = payload.get("sub")
    role = payload.get("role")
    if not exp or not sub or not role:
        raise _credentials_exception("Token missing required claims.")

    if int(exp) < int(datetime.now(timezone.utc).timestamp()):
        raise _credentials_exception("Token has expired.")

    payload["role"] = normalize_role(role)
    return payload


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
):
    """Return user object if credentials are valid."""
    user = await crud.get_user_by_username(db, username=username)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_user_from_token(db: AsyncSession, token: str):
    """Resolve user from bearer token."""
    if not settings.auth_enabled:
        return SystemPrincipal()

    payload = decode_access_token(token)
    username = payload.get("sub")
    user = await crud.get_user_by_username(db, username=username)
    if not user or not user.is_active:
        raise _credentials_exception("Inactive or unknown user.")
    return user


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Dependency returning the current authenticated user."""
    if not settings.auth_enabled:
        user = SystemPrincipal()
        request.state.current_user = user
        return user

    if not token:
        raise _credentials_exception("Missing bearer token.")

    user = await get_user_from_token(db, token)
    request.state.current_user = user
    return user


def require_roles(*allowed_roles: UserRole | str):
    """Create a dependency that enforces role membership."""
    normalized: set[str] = set()
    for role in allowed_roles:
        role_value = role.value if isinstance(role, UserRole) else role
        normalized.add(normalize_role(role_value))

    async def _dependency(
        request: Request,
        current_user=Depends(get_current_user),
    ):
        if settings.auth_enabled and normalize_role(current_user.role) not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions.",
            )
        request.state.current_user = current_user
        return current_user

    return _dependency


async def ensure_bootstrap_admin(db: AsyncSession) -> bool:
    """Ensure a bootstrap admin user exists."""
    if not settings.auth_enabled:
        return False

    username = settings.bootstrap_admin_username.strip()
    password = settings.bootstrap_admin_password
    if not username or not password:
        return False

    existing = await crud.get_user_by_username(db, username=username)
    if existing:
        return False

    hashed = hash_password(password)
    await crud.create_user(
        db=db,
        username=username,
        full_name=settings.bootstrap_admin_full_name,
        role=UserRole.ADMIN.value,
        hashed_password=hashed,
        is_active=True,
    )
    return True


def is_default_bootstrap_password() -> bool:
    return settings.bootstrap_admin_password == "admin12345"


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _json_bytes(data: dict) -> bytes:
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _credentials_exception(detail: str = "Could not validate credentials.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
