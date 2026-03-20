from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import List, Optional

from app.db.models import AuditLog, ConsentRecord, ConversationSession, DataExportLog, IntakeSession, RefreshToken, User

async def create_session(db: AsyncSession, session_data: dict) -> IntakeSession:
    db_session = IntakeSession(
        patient_name=session_data.get("patient_name"),
        transcript=session_data.get("transcript"),
        detected_language=session_data.get("detected_language", "en"),
        chief_complaint=session_data.get("chief_complaint"),
        soap_subjective=session_data.get("soap_subjective"),
        soap_objective=session_data.get("soap_objective"),
        soap_assessment=session_data.get("soap_assessment"),
        soap_plan=session_data.get("soap_plan")
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    return db_session


async def get_sessions(db: AsyncSession, skip: int = 0, limit: int = 50) -> List[IntakeSession]:
    result = await db.execute(select(IntakeSession).order_by(desc(IntakeSession.created_at)).offset(skip).limit(limit))
    return result.scalars().all()


async def get_session_by_id(db: AsyncSession, session_id: str) -> Optional[IntakeSession]:
    result = await db.execute(select(IntakeSession).where(IntakeSession.id == session_id))
    return result.scalar_one_or_none()


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    db_session = await get_session_by_id(db, session_id)
    if db_session:
        await db.delete(db_session)
        await db.commit()
        return True
    return False


async def create_user(
    db: AsyncSession,
    username: str,
    full_name: Optional[str],
    role: str,
    hashed_password: str,
    is_active: bool = True,
) -> User:
    user = User(
        username=username,
        full_name=full_name,
        role=role,
        hashed_password=hashed_password,
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
    result = await db.execute(select(User).order_by(User.username).offset(skip).limit(limit))
    return result.scalars().all()


async def create_audit_log(
    db: AsyncSession,
    *,
    user_id: Optional[str],
    username: Optional[str],
    role: Optional[str],
    action: str,
    resource: str,
    endpoint: str,
    http_method: str,
    status_code: int,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[str] = None,
    data_access_type: Optional[str] = None,
    phi_accessed: bool = False,
    correlation_id: Optional[str] = None,
) -> AuditLog:
    audit_log = AuditLog(
        user_id=user_id,
        username=username,
        role=role,
        action=action,
        resource=resource,
        resource_id=resource_id,
        endpoint=endpoint,
        http_method=http_method,
        status_code=status_code,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        data_access_type=data_access_type,
        phi_accessed=phi_accessed,
        correlation_id=correlation_id,
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(audit_log)
    return audit_log


async def get_audit_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 200,
    username: Optional[str] = None,
    resource: Optional[str] = None,
    data_access_type: Optional[str] = None,
    phi_only: bool = False,
) -> List[AuditLog]:
    stmt = select(AuditLog).order_by(desc(AuditLog.timestamp)).offset(skip).limit(limit)
    if username:
        stmt = stmt.where(AuditLog.username == username)
    if resource:
        stmt = stmt.where(AuditLog.resource == resource)
    if data_access_type:
        stmt = stmt.where(AuditLog.data_access_type == data_access_type)
    if phi_only:
        stmt = stmt.where(AuditLog.phi_accessed == True)

    result = await db.execute(stmt)
    return result.scalars().all()


# =====================================================
# Conversation Session CRUD
# =====================================================

async def create_conversation_session(
    db: AsyncSession,
    session_data: dict,
) -> ConversationSession:
    conv = ConversationSession(
        id=session_data.get("session_id"),
        mode=session_data.get("mode", "patient"),
        state=session_data.get("state", "ended"),
        turns_json=session_data.get("turns_json"),
        accumulated_transcript=session_data.get("accumulated_transcript"),
        entities_json=session_data.get("entities_json"),
        intake_session_id=session_data.get("intake_session_id"),
        ended_at=session_data.get("ended_at"),
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_conversation_session(
    db: AsyncSession, session_id: str
) -> Optional[ConversationSession]:
    result = await db.execute(
        select(ConversationSession).where(ConversationSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_conversation_sessions(
    db: AsyncSession, skip: int = 0, limit: int = 50
) -> List[ConversationSession]:
    result = await db.execute(
        select(ConversationSession)
        .order_by(desc(ConversationSession.created_at))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def create_export_log(
    db: AsyncSession,
    *,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    export_type: str,
    resource_type: str,
    resource_ids: Optional[str] = None,
    record_count: int = 0,
    destination: Optional[str] = None,
    ip_address: Optional[str] = None,
    status: str = "success",
    details: Optional[str] = None,
) -> DataExportLog:
    export_log = DataExportLog(
        user_id=user_id,
        username=username,
        export_type=export_type,
        resource_type=resource_type,
        resource_ids=resource_ids,
        record_count=record_count,
        destination=destination,
        ip_address=ip_address,
        status=status,
        details=details,
    )
    db.add(export_log)
    await db.commit()
    await db.refresh(export_log)
    return export_log


async def get_export_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 200,
    username: Optional[str] = None,
    export_type: Optional[str] = None,
) -> List[DataExportLog]:
    stmt = select(DataExportLog).order_by(desc(DataExportLog.timestamp)).offset(skip).limit(limit)
    if username:
        stmt = stmt.where(DataExportLog.username == username)
    if export_type:
        stmt = stmt.where(DataExportLog.export_type == export_type)

    result = await db.execute(stmt)
    return result.scalars().all()


# =====================================================
# Refresh Token CRUD (Phase 4)
# =====================================================

async def create_refresh_token(
    db: AsyncSession,
    user_id: str,
    token_hash: str,
    expires_at,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RefreshToken:
    rt = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(rt)
    await db.commit()
    await db.refresh(rt)
    return rt


async def get_refresh_token_by_hash(db: AsyncSession, token_hash: str) -> Optional[RefreshToken]:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, token_hash: str) -> bool:
    rt = await get_refresh_token_by_hash(db, token_hash)
    if rt:
        rt.revoked = True
        await db.commit()
        return True
    return False


async def revoke_all_user_tokens(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    tokens = result.scalars().all()
    for t in tokens:
        t.revoked = True
    await db.commit()
    return len(tokens)


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    from datetime import datetime
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.expires_at < datetime.utcnow())
    )
    expired = result.scalars().all()
    for t in expired:
        await db.delete(t)
    await db.commit()
    return len(expired)


# =====================================================
# Consent Record CRUD (Phase 4)
# =====================================================

async def create_consent_record(
    db: AsyncSession,
    session_id: str,
    consent_type: str = "verbal",
    patient_identifier: Optional[str] = None,
    recorded_by_user_id: Optional[str] = None,
    recorded_by_username: Optional[str] = None,
    details: Optional[str] = None,
) -> ConsentRecord:
    record = ConsentRecord(
        session_id=session_id,
        consent_type=consent_type,
        patient_identifier=patient_identifier,
        recorded_by_user_id=recorded_by_user_id,
        recorded_by_username=recorded_by_username,
        details=details,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_consent_for_session(db: AsyncSession, session_id: str) -> Optional[ConsentRecord]:
    result = await db.execute(
        select(ConsentRecord).where(
            ConsentRecord.session_id == session_id,
            ConsentRecord.revoked == False,
        )
    )
    return result.scalar_one_or_none()


async def revoke_consent(db: AsyncSession, consent_id: str) -> bool:
    from datetime import datetime
    result = await db.execute(
        select(ConsentRecord).where(ConsentRecord.id == consent_id)
    )
    record = result.scalar_one_or_none()
    if record and not record.revoked:
        record.revoked = True
        record.revoked_at = datetime.utcnow()
        await db.commit()
        return True
    return False


async def list_consent_records(
    db: AsyncSession, skip: int = 0, limit: int = 50
) -> List[ConsentRecord]:
    result = await db.execute(
        select(ConsentRecord)
        .order_by(desc(ConsentRecord.consented_at))
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# =====================================================
# User MFA Updates (Phase 4)
# =====================================================

async def update_user_totp(db: AsyncSession, user_id: str, totp_secret: Optional[str]) -> Optional[User]:
    from datetime import datetime
    user = await get_user_by_id(db, user_id)
    if user:
        user.totp_secret = totp_secret
        user.mfa_enrolled_at = datetime.utcnow() if totp_secret else None
        await db.commit()
        await db.refresh(user)
    return user


async def deactivate_user(db: AsyncSession, user_id: str) -> bool:
    user = await get_user_by_id(db, user_id)
    if user:
        user.is_active = False
        await db.commit()
        return True
    return False


async def count_users(db: AsyncSession) -> int:
    from sqlalchemy import func
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar() or 0
