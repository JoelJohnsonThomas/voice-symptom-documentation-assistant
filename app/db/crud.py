from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import List, Optional

from app.db.models import AuditLog, DataExportLog, IntakeSession, User

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
