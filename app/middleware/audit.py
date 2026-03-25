"""
Audit logging helpers for HIPAA compliance.

Extracted from main.py. Provides helper functions for writing audit logs
and deriving audit metadata from HTTP requests.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db import crud
from app.logging_config import correlation_id_var

logger = logging.getLogger(__name__)


def extract_client_ip(request) -> Optional[str]:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def derive_audit_resource(path: str) -> tuple[str, Optional[str]]:
    """Derive the resource name and optional resource ID from a URL path."""
    parts = [segment for segment in path.split("/") if segment]
    if not parts:
        return "unknown", None
    if parts[0] == "api":
        if len(parts) == 1:
            return "api", None
        resource = parts[1]
        resource_id = parts[2] if len(parts) > 2 else None
        return resource, resource_id
    return parts[0], parts[1] if len(parts) > 1 else None


def derive_audit_action(method: str, path: str) -> str:
    """Derive the audit action from HTTP method."""
    method_upper = method.upper()
    if method_upper == "GET":
        return "read"
    if method_upper == "POST":
        return "create"
    if method_upper in {"PUT", "PATCH"}:
        return "update"
    if method_upper == "DELETE":
        return "delete"
    return method.lower() if method else "access"


async def write_audit_log(
    *,
    request_path: str,
    request_method: str,
    status_code: int,
    user=None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[str] = None,
    data_access_type: Optional[str] = None,
    phi_accessed: bool = False,
) -> None:
    """Write an audit log entry for HIPAA compliance.

    No-op if audit_logging_enabled is False.
    """
    if not settings.audit_logging_enabled:
        return

    resource, resource_id = derive_audit_resource(request_path)
    action = derive_audit_action(request_method, request_path)

    if data_access_type is None:
        data_access_type = {
            "read": "read",
            "create": "write",
            "update": "write",
            "delete": "delete",
        }.get(action)

    cid = correlation_id_var.get()

    async with AsyncSessionLocal() as audit_db:
        try:
            await crud.create_audit_log(
                db=audit_db,
                user_id=getattr(user, "id", None),
                username=getattr(user, "username", None),
                role=getattr(user, "role", None),
                action=action,
                resource=resource,
                resource_id=resource_id,
                endpoint=request_path,
                http_method=request_method.upper(),
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                data_access_type=data_access_type,
                phi_accessed=phi_accessed,
                correlation_id=cid,
            )
        except Exception as exc:
            logger.warning(f"Failed to write audit log: {exc}")


async def check_consent_if_required(session_id: str) -> None:
    """Check consent is recorded for a session when consent tracking is enabled.

    Raises HTTP 428 (Precondition Required) if consent is missing.
    """
    from fastapi import HTTPException

    if not settings.consent_tracking_enabled:
        return
    async with AsyncSessionLocal() as db:
        record = await crud.get_consent_for_session(db, session_id)
        if not record or record.revoked:
            raise HTTPException(
                status_code=428,
                detail="Patient consent required before intake processing. "
                       "Record consent via POST /api/auth/consent/record first.",
            )
