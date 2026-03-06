"""
HIPAA Data Retention Policies & Auto-Purge

Provides:
- Configurable retention periods for intake sessions and audit logs
- Scheduled background auto-purge of expired data
- Manual purge trigger for admin use
- Purge logging for compliance audit trail
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import AuditLog, IntakeSession

logger = logging.getLogger(__name__)

_purge_task: Optional[asyncio.Task] = None


async def purge_expired_sessions(db: AsyncSession) -> int:
    """Delete intake sessions older than the retention period.

    Returns the number of deleted records.
    """
    if settings.retention_sessions_days <= 0:
        return 0  # Retention disabled (keep forever)

    cutoff = datetime.utcnow() - timedelta(days=settings.retention_sessions_days)

    # Count first for logging
    count_result = await db.execute(
        select(func.count()).select_from(IntakeSession).where(
            IntakeSession.created_at < cutoff
        )
    )
    count = count_result.scalar() or 0

    if count > 0:
        await db.execute(
            delete(IntakeSession).where(IntakeSession.created_at < cutoff)
        )
        await db.commit()
        logger.info(f"Purged {count} expired intake sessions (older than {settings.retention_sessions_days} days)")

    return count


async def purge_expired_audit_logs(db: AsyncSession) -> int:
    """Delete audit logs older than the retention period.

    Returns the number of deleted records.
    Note: HIPAA requires minimum 6 years for audit logs.
    """
    if settings.retention_audit_logs_days <= 0:
        return 0  # Retention disabled (keep forever)

    cutoff = datetime.utcnow() - timedelta(days=settings.retention_audit_logs_days)

    count_result = await db.execute(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.timestamp < cutoff
        )
    )
    count = count_result.scalar() or 0

    if count > 0:
        await db.execute(
            delete(AuditLog).where(AuditLog.timestamp < cutoff)
        )
        await db.commit()
        logger.info(f"Purged {count} expired audit logs (older than {settings.retention_audit_logs_days} days)")

    return count


async def run_purge() -> dict:
    """Execute a full purge cycle and return results."""
    results = {"sessions_purged": 0, "audit_logs_purged": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        try:
            results["sessions_purged"] = await purge_expired_sessions(db)
        except Exception as exc:
            logger.error(f"Session purge failed: {exc}")
            results["errors"].append(f"session_purge: {exc}")

        try:
            results["audit_logs_purged"] = await purge_expired_audit_logs(db)
        except Exception as exc:
            logger.error(f"Audit log purge failed: {exc}")
            results["errors"].append(f"audit_log_purge: {exc}")

    return results


async def get_retention_stats() -> dict:
    """Get current retention statistics for the admin dashboard."""
    async with AsyncSessionLocal() as db:
        session_count = await db.execute(
            select(func.count()).select_from(IntakeSession)
        )
        audit_count = await db.execute(
            select(func.count()).select_from(AuditLog)
        )

        # Count records that would be purged
        sessions_total = session_count.scalar() or 0
        audits_total = audit_count.scalar() or 0

        sessions_expired = 0
        audits_expired = 0

        if settings.retention_sessions_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=settings.retention_sessions_days)
            result = await db.execute(
                select(func.count()).select_from(IntakeSession).where(
                    IntakeSession.created_at < cutoff
                )
            )
            sessions_expired = result.scalar() or 0

        if settings.retention_audit_logs_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=settings.retention_audit_logs_days)
            result = await db.execute(
                select(func.count()).select_from(AuditLog).where(
                    AuditLog.timestamp < cutoff
                )
            )
            audits_expired = result.scalar() or 0

    return {
        "sessions": {
            "total": sessions_total,
            "expired": sessions_expired,
            "retention_days": settings.retention_sessions_days,
        },
        "audit_logs": {
            "total": audits_total,
            "expired": audits_expired,
            "retention_days": settings.retention_audit_logs_days,
        },
        "auto_purge_enabled": settings.auto_purge_enabled,
        "purge_interval_hours": settings.auto_purge_interval_hours,
    }


async def _purge_loop():
    """Background loop that periodically runs the purge cycle."""
    interval = settings.auto_purge_interval_hours * 3600
    logger.info(
        f"Auto-purge scheduler started (interval: {settings.auto_purge_interval_hours}h, "
        f"sessions: {settings.retention_sessions_days}d, "
        f"audit logs: {settings.retention_audit_logs_days}d)"
    )

    while True:
        try:
            await asyncio.sleep(interval)
            if settings.auto_purge_enabled:
                results = await run_purge()
                if results["sessions_purged"] or results["audit_logs_purged"]:
                    logger.info(f"Auto-purge completed: {results}")
        except asyncio.CancelledError:
            logger.info("Auto-purge scheduler stopped.")
            break
        except Exception as exc:
            logger.error(f"Auto-purge cycle error: {exc}")


def start_purge_scheduler():
    """Start the background purge scheduler."""
    global _purge_task
    if not settings.auto_purge_enabled:
        logger.info("Auto-purge is disabled by configuration.")
        return
    if _purge_task is not None:
        return  # Already running

    _purge_task = asyncio.ensure_future(_purge_loop())


def stop_purge_scheduler():
    """Stop the background purge scheduler."""
    global _purge_task
    if _purge_task is not None:
        _purge_task.cancel()
        _purge_task = None
