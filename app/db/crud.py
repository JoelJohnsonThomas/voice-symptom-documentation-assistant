from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import List, Optional

from app.db.models import IntakeSession

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
