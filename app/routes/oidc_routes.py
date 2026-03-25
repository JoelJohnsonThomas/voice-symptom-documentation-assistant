"""
OAuth2/OIDC SSO Routes

Supports enterprise SSO providers (Okta, Azure AD, Google, etc.) via
the Authorization Code flow with PKCE. Maps OIDC claims to internal
UserRole for RBAC enforcement.

Configuration:
    OIDC_ENABLED=true
    OIDC_ISSUER_URL=https://accounts.google.com
    OIDC_CLIENT_ID=your-client-id
    OIDC_CLIENT_SECRET=your-client-secret
    OIDC_REDIRECT_URI=https://your-app.com/api/auth/oidc/callback
    OIDC_SCOPES=openid email profile
    OIDC_ROLE_CLAIM=role
    OIDC_DEFAULT_ROLE=viewer
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/oidc", tags=["oidc"])

# Lazy-initialized OIDC client
_oauth_client = None


def _get_oauth_client():
    """Lazily initialize the OIDC client using authlib."""
    global _oauth_client
    if _oauth_client is not None:
        return _oauth_client

    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC is not enabled")

    if not settings.oidc_issuer_url or not settings.oidc_client_id:
        raise HTTPException(
            status_code=503,
            detail="OIDC not configured: OIDC_ISSUER_URL and OIDC_CLIENT_ID required",
        )

    try:
        from authlib.integrations.starlette_client import OAuth
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="authlib not installed. Install with: pip install authlib",
        )

    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        server_metadata_url=f"{settings.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration",
        client_kwargs={"scope": settings.oidc_scopes},
    )
    _oauth_client = oauth
    return _oauth_client


@router.get("/login")
async def oidc_login(request: Request):
    """Redirect to the OIDC provider's authorization endpoint.

    The frontend should redirect the user to this endpoint to begin
    the SSO login flow.
    """
    oauth = _get_oauth_client()
    redirect_uri = settings.oidc_redirect_uri
    if not redirect_uri:
        # Infer from current request
        redirect_uri = str(request.url_for("oidc_callback"))

    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def oidc_callback(request: Request):
    """Handle the OIDC provider's callback after user authentication.

    Exchanges the authorization code for tokens, extracts user info,
    creates or updates the local user record, and issues JWT tokens.
    """
    oauth = _get_oauth_client()

    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception as e:
        logger.error(f"OIDC token exchange failed: {e}")
        raise HTTPException(status_code=401, detail=f"OIDC authentication failed: {e}")

    # Extract user info from ID token or userinfo endpoint
    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = await oauth.oidc.userinfo(token=token)
        except Exception:
            userinfo = {}

    if not userinfo:
        raise HTTPException(status_code=401, detail="Could not retrieve user info from OIDC provider")

    email = userinfo.get("email", "")
    name = userinfo.get("name", email)
    sub = userinfo.get("sub", "")

    if not email and not sub:
        raise HTTPException(status_code=401, detail="OIDC response missing email and sub claims")

    # Map OIDC role claim to internal role
    from app.auth import UserRole, create_access_token, create_refresh_token, hash_token

    oidc_role = userinfo.get(settings.oidc_role_claim, settings.oidc_default_role)
    try:
        role = UserRole(oidc_role)
    except ValueError:
        role = UserRole(settings.oidc_default_role)

    # Find or create local user
    from app.db.database import AsyncSessionLocal
    from app.db import crud

    username = email or f"oidc_{sub}"

    async with AsyncSessionLocal() as db:
        user = await crud.get_user_by_username(db, username)

        if not user:
            # Create new user (no password needed for OIDC-only users)
            from app.auth import hash_password
            user = await crud.create_user(
                db,
                username=username,
                hashed_password=hash_password(uuid.uuid4().hex),  # Random, unused password
                full_name=name,
                role=role.value,
            )
            logger.info(f"Created OIDC user: {username} with role {role.value}")
        else:
            logger.info(f"OIDC login for existing user: {username}")

        # Issue JWT tokens
        access_token = create_access_token(user.id, user.role)
        refresh_token = create_refresh_token(user.id)

        await crud.create_refresh_token(
            db,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    # Redirect to frontend with tokens (or return JSON)
    # For SPA apps, redirect with tokens in fragment
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        # Browser redirect — pass tokens via URL fragment (not query params for security)
        redirect_url = f"/static/index.html#access_token={access_token}&token_type=bearer"
        return RedirectResponse(url=redirect_url)

    # API client — return JSON
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        },
    }


@router.get("/status")
async def oidc_status():
    """Return OIDC configuration status."""
    return {
        "oidc_enabled": settings.oidc_enabled,
        "issuer_url": settings.oidc_issuer_url if settings.oidc_enabled else None,
    }
