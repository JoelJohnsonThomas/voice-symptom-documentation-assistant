"""Clinician SOAP review API: versioning, annotations, and approval workflow.

Exposes the ``DocumentVersion`` and ``DocumentAnnotation`` tables so clinicians
can edit, annotate, and approve AI-generated SOAP notes. All write operations
emit HIPAA audit logs and increment Prometheus counters.

COMPLIANCE: All endpoints handle PHI. Audit logs record every read/write with
``phi_accessed=True`` and rely on the global encryption-at-rest setting for
storage of SOAP content.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import UserRole, get_current_user, require_roles
from app.config import settings
from app.db import crud
from app.db.database import get_db
from app.db.models import DocumentAnnotation, DocumentVersion
from app.encryption import decrypt_data, encrypt_data
from app.metrics import SOAP_ANNOTATION_COUNT, SOAP_APPROVAL_COUNT, SOAP_VERSION_COUNT
from app.middleware.audit import extract_client_ip, write_audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["soap-review"])

MAX_CONTENT_BYTES = 1_000_000  # 1 MB cap on SOAP payloads

ALLOWED_CHANGE_TYPES = {"initial", "edit", "ai_generated", "review", "correction"}
ALLOWED_SECTIONS = {"subjective", "objective", "assessment", "plan"}
ALLOWED_ANNOTATION_TYPES = {"correction", "addition", "question", "approval", "flag"}
ALLOWED_ANNOTATION_STATUSES = {"open", "resolved", "rejected"}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SOAPContent(BaseModel):
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None


class VersionCreateRequest(BaseModel):
    content: SOAPContent
    change_summary: Optional[str] = Field(default=None, max_length=500)
    change_type: str = Field(default="edit")
    confidence: Optional[dict] = None


class VersionSummary(BaseModel):
    id: str
    session_id: str
    version_number: int
    created_at: datetime
    author_id: Optional[str]
    author_username: Optional[str]
    author_role: Optional[str]
    change_type: str
    change_summary: Optional[str]


class VersionDetail(VersionSummary):
    content: SOAPContent
    diff: Optional[dict] = None
    confidence: Optional[dict] = None


class AnnotationCreateRequest(BaseModel):
    document_version_id: str
    soap_section: str
    annotation_type: str
    content: str = Field(..., min_length=1, max_length=4000)
    field_path: Optional[str] = None
    text_offset_start: Optional[int] = None
    text_offset_end: Optional[int] = None
    suggested_replacement: Optional[str] = Field(default=None, max_length=4000)


class AnnotationUpdateRequest(BaseModel):
    status: str


class AnnotationOut(BaseModel):
    id: str
    document_version_id: str
    session_id: str
    created_at: datetime
    author_id: Optional[str]
    author_username: Optional[str]
    soap_section: str
    field_path: Optional[str]
    text_offset_start: Optional[int]
    text_offset_end: Optional[int]
    annotation_type: str
    content: str
    suggested_replacement: Optional[str]
    status: str
    resolved_by_id: Optional[str]
    resolved_at: Optional[datetime]


class ApprovalResponse(BaseModel):
    annotation: AnnotationOut
    session_approved: bool
    approved_sections: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_content(version: DocumentVersion) -> SOAPContent:
    raw = version.content_json or "{}"
    if version.is_encrypted:
        raw = decrypt_data(raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    return SOAPContent(**{k: payload.get(k) for k in ALLOWED_SECTIONS})


def _encode_content(content: SOAPContent) -> tuple[str, bool]:
    body = json.dumps(content.model_dump(), ensure_ascii=False)
    if len(body.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise HTTPException(status_code=413, detail="SOAP payload exceeds 1MB cap")
    if settings.encryption_at_rest_enabled:
        return encrypt_data(body), True
    return body, False


def _diff_versions(prev: Optional[SOAPContent], curr: SOAPContent) -> dict:
    """Compute a per-section diff between two SOAP snapshots."""
    prev_payload = prev.model_dump() if prev else {k: None for k in ALLOWED_SECTIONS}
    curr_payload = curr.model_dump()
    changes = {}
    for section in ALLOWED_SECTIONS:
        before = prev_payload.get(section)
        after = curr_payload.get(section)
        if before != after:
            changes[section] = {"before": before, "after": after}
    return changes


def _version_to_summary(version: DocumentVersion) -> VersionSummary:
    return VersionSummary(
        id=version.id,
        session_id=version.session_id,
        version_number=version.version_number,
        created_at=version.created_at,
        author_id=version.author_id,
        author_username=version.author_username,
        author_role=version.author_role,
        change_type=version.change_type,
        change_summary=version.change_summary,
    )


def _annotation_to_out(annotation: DocumentAnnotation) -> AnnotationOut:
    return AnnotationOut(
        id=annotation.id,
        document_version_id=annotation.document_version_id,
        session_id=annotation.session_id,
        created_at=annotation.created_at,
        author_id=annotation.author_id,
        author_username=annotation.author_username,
        soap_section=annotation.soap_section,
        field_path=annotation.field_path,
        text_offset_start=annotation.text_offset_start,
        text_offset_end=annotation.text_offset_end,
        annotation_type=annotation.annotation_type,
        content=annotation.content,
        suggested_replacement=annotation.suggested_replacement,
        status=annotation.status,
        resolved_by_id=annotation.resolved_by_id,
        resolved_at=annotation.resolved_at,
    )


async def _audit(request: Request, user, action: str, resource_id: Optional[str], status_code: int, details: Optional[str] = None) -> None:
    if not settings.audit_logging_enabled:
        return
    try:
        await write_audit_log(
            request_path=request.url.path,
            request_method=request.method,
            status_code=status_code,
            user=user,
            ip_address=extract_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=details if details else f"resource_id={resource_id}" if resource_id else None,
            data_access_type="phi",
            phi_accessed=True,
        )
    except Exception:  # pragma: no cover — audit failures must not break the API
        logger.exception("Failed to write SOAP review audit log")


async def _latest_version(db: AsyncSession, session_id: str) -> Optional[DocumentVersion]:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.session_id == session_id)
        .order_by(desc(DocumentVersion.version_number))
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Version routes
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/versions", response_model=list[VersionSummary])
async def list_versions(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List all SOAP versions for a session, newest first."""
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.session_id == session_id)
        .order_by(desc(DocumentVersion.version_number))
    )
    versions = result.scalars().all()
    summaries = [_version_to_summary(v) for v in versions]
    await _audit(request, user, "read", session_id, 200, f"versions_listed={len(summaries)}")
    return summaries


@router.get("/sessions/{session_id}/versions/{version_id}", response_model=VersionDetail)
async def get_version(
    session_id: str,
    version_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Return a single SOAP version with decrypted content + diff."""
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.session_id == session_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    content = _decode_content(version)
    diff = json.loads(version.diff_json) if version.diff_json else None
    confidence = json.loads(version.confidence_json) if version.confidence_json else None

    summary = _version_to_summary(version)
    detail = VersionDetail(**summary.model_dump(), content=content, diff=diff, confidence=confidence)
    await _audit(request, user, "read", version_id, 200)
    return detail


@router.post(
    "/sessions/{session_id}/versions",
    response_model=VersionDetail,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROVIDER))],
)
async def create_version(
    session_id: str,
    payload: VersionCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create a new SOAP version. Only clinicians (PROVIDER/ADMIN) may edit."""
    if payload.change_type not in ALLOWED_CHANGE_TYPES:
        raise HTTPException(status_code=400, detail=f"change_type must be one of {sorted(ALLOWED_CHANGE_TYPES)}")

    previous = await _latest_version(db, session_id)
    next_number = (previous.version_number + 1) if previous else 1
    prev_content = _decode_content(previous) if previous else None
    diff = _diff_versions(prev_content, payload.content)

    encoded_content, was_encrypted = _encode_content(payload.content)

    version = DocumentVersion(
        session_id=session_id,
        version_number=next_number,
        author_id=getattr(user, "id", None),
        author_username=getattr(user, "username", None),
        author_role=getattr(user, "role", None),
        content_json=encoded_content,
        diff_json=json.dumps(diff) if diff else None,
        change_summary=payload.change_summary,
        change_type=payload.change_type,
        confidence_json=json.dumps(payload.confidence) if payload.confidence else None,
        is_encrypted=was_encrypted,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)

    SOAP_VERSION_COUNT.inc(change_type=payload.change_type)

    await _audit(request, user, "create", version.id, 201, f"version_number={next_number}")

    summary = _version_to_summary(version)
    return VersionDetail(**summary.model_dump(), content=payload.content, diff=diff or None, confidence=payload.confidence)


# ---------------------------------------------------------------------------
# Approval route
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/versions/{version_id}/approve",
    response_model=ApprovalResponse,
    status_code=201,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.PROVIDER))],
)
async def approve_version(
    session_id: str,
    version_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Approve a SOAP version. Creates a resolved approval annotation per section.

    Returns the most recent approval annotation and a rollup flag indicating
    whether every SOAP section now has at least one approval on this version.
    """
    version_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.session_id == session_id,
        )
    )
    version = version_result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    now = datetime.utcnow()
    created: list[DocumentAnnotation] = []
    for section in sorted(ALLOWED_SECTIONS):
        annotation = DocumentAnnotation(
            document_version_id=version_id,
            session_id=session_id,
            author_id=getattr(user, "id", None),
            author_username=getattr(user, "username", None),
            soap_section=section,
            annotation_type="approval",
            content=f"Approved by {getattr(user, 'username', 'unknown')}",
            status="resolved",
            resolved_by_id=getattr(user, "id", None),
            resolved_at=now,
        )
        db.add(annotation)
        created.append(annotation)

    await db.commit()
    for a in created:
        await db.refresh(a)

    SOAP_APPROVAL_COUNT.inc()

    approved_result = await db.execute(
        select(DocumentAnnotation.soap_section)
        .where(
            DocumentAnnotation.document_version_id == version_id,
            DocumentAnnotation.annotation_type == "approval",
            DocumentAnnotation.status == "resolved",
        )
        .distinct()
    )
    approved_sections = sorted({row[0] for row in approved_result.all()})
    session_approved = set(approved_sections) >= ALLOWED_SECTIONS

    await _audit(request, user, "create", version_id, 201, "soap_approved")

    return ApprovalResponse(
        annotation=_annotation_to_out(created[-1]),
        session_approved=session_approved,
        approved_sections=approved_sections,
    )


# ---------------------------------------------------------------------------
# Annotation routes
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/annotations", response_model=list[AnnotationOut])
async def list_annotations(
    session_id: str,
    request: Request,
    soap_section: Optional[str] = None,
    annotation_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """List annotations for a session, filterable by section and status."""
    stmt = select(DocumentAnnotation).where(DocumentAnnotation.session_id == session_id)
    if soap_section:
        if soap_section not in ALLOWED_SECTIONS:
            raise HTTPException(status_code=400, detail="invalid soap_section")
        stmt = stmt.where(DocumentAnnotation.soap_section == soap_section)
    if annotation_status:
        if annotation_status not in ALLOWED_ANNOTATION_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status filter")
        stmt = stmt.where(DocumentAnnotation.status == annotation_status)
    stmt = stmt.order_by(desc(DocumentAnnotation.created_at))

    result = await db.execute(stmt)
    annotations = result.scalars().all()
    out = [_annotation_to_out(a) for a in annotations]
    await _audit(request, user, "read", session_id, 200, f"annotations_listed={len(out)}")
    return out


@router.post(
    "/sessions/{session_id}/annotations",
    response_model=AnnotationOut,
    status_code=201,
)
async def create_annotation(
    session_id: str,
    payload: AnnotationCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Create an annotation on a SOAP version. Any authenticated user may comment."""
    if payload.soap_section not in ALLOWED_SECTIONS:
        raise HTTPException(status_code=400, detail=f"soap_section must be one of {sorted(ALLOWED_SECTIONS)}")
    if payload.annotation_type not in ALLOWED_ANNOTATION_TYPES:
        raise HTTPException(status_code=400, detail=f"annotation_type must be one of {sorted(ALLOWED_ANNOTATION_TYPES)}")

    if payload.annotation_type == "approval":
        role = getattr(user, "role", None)
        role_value = role.value if hasattr(role, "value") else role
        if role_value not in {UserRole.ADMIN.value, UserRole.PROVIDER.value}:
            raise HTTPException(status_code=403, detail="Only clinicians may file approval annotations")

    version_check = await db.execute(
        select(DocumentVersion.id).where(
            DocumentVersion.id == payload.document_version_id,
            DocumentVersion.session_id == session_id,
        )
    )
    if version_check.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Referenced document version not found in this session")

    annotation = DocumentAnnotation(
        document_version_id=payload.document_version_id,
        session_id=session_id,
        author_id=getattr(user, "id", None),
        author_username=getattr(user, "username", None),
        soap_section=payload.soap_section,
        field_path=payload.field_path,
        text_offset_start=payload.text_offset_start,
        text_offset_end=payload.text_offset_end,
        annotation_type=payload.annotation_type,
        content=payload.content,
        suggested_replacement=payload.suggested_replacement,
        status="resolved" if payload.annotation_type == "approval" else "open",
    )
    if payload.annotation_type == "approval":
        annotation.resolved_by_id = getattr(user, "id", None)
        annotation.resolved_at = datetime.utcnow()

    db.add(annotation)
    await db.commit()
    await db.refresh(annotation)

    SOAP_ANNOTATION_COUNT.inc(annotation_type=payload.annotation_type)
    if payload.annotation_type == "approval":
        SOAP_APPROVAL_COUNT.inc()

    await _audit(request, user, "create", annotation.id, 201, f"type={payload.annotation_type}")
    return _annotation_to_out(annotation)


@router.patch("/annotations/{annotation_id}", response_model=AnnotationOut)
async def update_annotation_status(
    annotation_id: str,
    payload: AnnotationUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Resolve or reject an annotation. Author or PROVIDER/ADMIN may transition status."""
    if payload.status not in ALLOWED_ANNOTATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(ALLOWED_ANNOTATION_STATUSES)}")

    result = await db.execute(select(DocumentAnnotation).where(DocumentAnnotation.id == annotation_id))
    annotation = result.scalar_one_or_none()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    user_role = getattr(user, "role", None)
    user_role_value = user_role.value if hasattr(user_role, "value") else user_role
    user_id = getattr(user, "id", None)
    is_clinician = user_role_value in {UserRole.ADMIN.value, UserRole.PROVIDER.value}
    is_author = annotation.author_id and annotation.author_id == user_id
    if not (is_clinician or is_author):
        raise HTTPException(status_code=403, detail="Only the author or a clinician may change annotation status")

    annotation.status = payload.status
    if payload.status in {"resolved", "rejected"}:
        annotation.resolved_by_id = user_id
        annotation.resolved_at = datetime.utcnow()
    else:
        annotation.resolved_by_id = None
        annotation.resolved_at = None

    await db.commit()
    await db.refresh(annotation)

    await _audit(request, user, "update", annotation.id, 200, f"status={payload.status}")
    return _annotation_to_out(annotation)
