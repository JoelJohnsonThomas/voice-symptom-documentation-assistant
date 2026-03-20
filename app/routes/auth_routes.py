"""Authentication, MFA, and consent API routes.

All auth endpoints are gated by ``settings.auth_enabled``.  When disabled,
``/api/auth/status`` returns ``{auth_enabled: false}`` and the remaining
endpoints return 404 so the frontend knows to skip the login flow.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    ALL_ROLES,
    SYSTEM_USER,
    UserRole,
    create_access_token,
    create_mfa_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    require_roles,
    verify_password,
)
from app.config import settings
from app.db import crud
from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = None
    role: str = Field(default="intake")


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None
    mfa_token: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class MFAVerifyRequest(BaseModel):
    totp_code: str = Field(..., min_length=6, max_length=6)


class ConsentRequest(BaseModel):
    session_id: str
    consent_type: str = Field(default="verbal")
    patient_identifier: Optional[str] = None
    details: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth status (always available)
# ---------------------------------------------------------------------------

@router.get("/status")
async def auth_status():
    """Public endpoint returning current auth configuration."""
    return {
        "auth_enabled": settings.auth_enabled,
        "mfa_enabled": settings.mfa_enabled,
        "session_timeout_minutes": settings.session_inactivity_timeout_minutes,
        "consent_tracking_enabled": settings.consent_tracking_enabled,
    }


# ---------------------------------------------------------------------------
# Helper to block endpoints when auth is disabled
# ---------------------------------------------------------------------------

def _require_auth_enabled():
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authentication is not enabled",
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.

    First-user bootstrap: when the users table is empty, anyone can create the
    first admin account.  After that, only admins can register new users.
    """
    _require_auth_enabled()

    # Validate role
    try:
        role = UserRole(body.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {[r.value for r in UserRole]}",
        )

    user_count = await crud.count_users(db)

    if user_count > 0:
        # Require admin auth for subsequent registrations
        current_user = await get_current_user(request, db)
        if UserRole(current_user.role) != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can register new users",
            )
    else:
        # First user must be admin
        role = UserRole.ADMIN

    # Check duplicate username
    existing = await crud.get_user_by_username(db, body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    hashed = hash_password(body.password)
    user = await crud.create_user(
        db,
        username=body.username,
        full_name=body.full_name,
        role=role.value,
        hashed_password=hashed,
    )

    logger.info("User registered: %s (role=%s, bootstrap=%s)", user.username, role.value, user_count == 0)

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "message": "User registered successfully",
    }


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with username/password.  If MFA is enrolled, a second step
    with ``mfa_token`` + ``totp_code`` is required."""
    _require_auth_enabled()

    # --- MFA second step ---
    if body.mfa_token and body.totp_code:
        payload = decode_token(body.mfa_token)
        if payload.get("type") != "mfa_pending":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA token")

        user = await crud.get_user_by_id(db, payload["sub"])
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(body.totp_code, valid_window=1):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")

        return await _issue_tokens(user, request, db)

    # --- Normal password step ---
    user = await crud.get_user_by_username(db, body.username)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    # If user has MFA enrolled, require TOTP
    if user.totp_secret and settings.mfa_enabled:
        # If TOTP code provided inline, verify immediately
        if body.totp_code:
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(body.totp_code, valid_window=1):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
            return await _issue_tokens(user, request, db)

        # Otherwise return MFA challenge
        mfa_token = create_mfa_token(user.id)
        return {
            "mfa_required": True,
            "mfa_token": mfa_token,
            "message": "MFA verification required",
        }

    return await _issue_tokens(user, request, db)


async def _issue_tokens(user, request: Request, db: AsyncSession) -> dict:
    """Generate access + refresh tokens and persist the refresh token hash."""
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)

    # Store hashed refresh token in DB
    await crud.create_refresh_token(
        db,
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    logger.info("User logged in: %s", user.username)

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "full_name": user.full_name,
            "mfa_enrolled": bool(user.totp_secret),
        },
    }


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access token."""
    _require_auth_enabled()

    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    # Verify refresh token exists and is not revoked
    rt = await crud.get_refresh_token_by_hash(db, hash_token(body.refresh_token))
    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")

    user = await crud.get_user_by_id(db, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    access = create_access_token(user.id, user.role)
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Revoke the given refresh token."""
    _require_auth_enabled()

    revoked = await crud.revoke_refresh_token(db, hash_token(body.refresh_token))
    if not revoked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token not found or already revoked")

    logger.info("User logged out: %s", getattr(current_user, "username", "unknown"))
    return {"message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# Current user profile
# ---------------------------------------------------------------------------

@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    """Return the authenticated user's profile."""
    _require_auth_enabled()

    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": getattr(current_user, "full_name", None),
        "role": current_user.role if isinstance(current_user.role, str) else current_user.role.value,
        "is_active": current_user.is_active,
        "mfa_enrolled": bool(getattr(current_user, "totp_secret", None)),
    }


# ---------------------------------------------------------------------------
# MFA enrollment
# ---------------------------------------------------------------------------

@router.post("/mfa/enroll")
async def mfa_enroll(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new TOTP secret and return the provisioning URI + QR code."""
    _require_auth_enabled()

    if not settings.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA is not enabled on this server")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.username,
        issuer_name="VoxDoc",
    )

    # Generate QR code as base64
    qr_base64 = None
    try:
        import qrcode
        import base64
        qr = qrcode.make(provisioning_uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    except ImportError:
        logger.debug("qrcode library not available for QR generation")

    # Store secret (not yet verified — user must confirm with a code)
    await crud.update_user_totp(db, current_user.id, secret)

    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "qr_code_base64": qr_base64,
        "message": "Scan the QR code with your authenticator app, then verify with /api/auth/mfa/verify",
    }


@router.post("/mfa/verify")
async def mfa_verify(
    body: MFAVerifyRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the TOTP code to confirm MFA enrollment."""
    _require_auth_enabled()

    if not current_user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA not enrolled. Call /api/auth/mfa/enroll first")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(body.totp_code, valid_window=1):
        # Remove the secret on failure so user can re-enroll
        await crud.update_user_totp(db, current_user.id, None)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code. Enrollment reset — try again")

    logger.info("MFA enrolled for user: %s", current_user.username)
    return {"message": "MFA enrolled successfully", "mfa_enrolled": True}


# ---------------------------------------------------------------------------
# Consent tracking
# ---------------------------------------------------------------------------

@router.post("/consent/record", status_code=status.HTTP_201_CREATED)
async def record_consent(
    body: ConsentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record patient consent for a session."""
    # Check for existing active consent
    existing = await crud.get_consent_for_session(db, body.session_id)
    if existing:
        return {
            "id": existing.id,
            "session_id": existing.session_id,
            "message": "Consent already recorded for this session",
        }

    user_id = getattr(current_user, "id", "system")
    username = getattr(current_user, "username", "system")

    record = await crud.create_consent_record(
        db,
        session_id=body.session_id,
        consent_type=body.consent_type,
        patient_identifier=body.patient_identifier,
        recorded_by_user_id=user_id,
        recorded_by_username=username,
        details=body.details,
    )

    logger.info("Consent recorded for session %s by %s", body.session_id, username)

    return {
        "id": record.id,
        "session_id": record.session_id,
        "consent_type": record.consent_type,
        "consented_at": record.consented_at.isoformat() if record.consented_at else None,
        "message": "Consent recorded successfully",
    }


@router.get("/consent/{session_id}")
async def get_consent(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Check if consent exists for a session."""
    record = await crud.get_consent_for_session(db, session_id)
    if not record:
        return {"session_id": session_id, "has_consent": False}

    return {
        "session_id": session_id,
        "has_consent": True,
        "consent_id": record.id,
        "consent_type": record.consent_type,
        "consented_at": record.consented_at.isoformat() if record.consented_at else None,
    }


@router.post("/consent/{consent_id}/revoke")
async def revoke_consent_endpoint(
    consent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Revoke a consent record."""
    revoked = await crud.revoke_consent(db, consent_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found or already revoked")

    logger.info("Consent %s revoked by %s", consent_id, getattr(current_user, "username", "unknown"))
    return {"message": "Consent revoked successfully", "consent_id": consent_id}
