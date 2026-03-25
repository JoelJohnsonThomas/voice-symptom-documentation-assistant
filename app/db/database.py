"""Database engine configuration.

Phase 8: Supports PostgreSQL (via asyncpg) alongside SQLite (via aiosqlite).
Set ``DATABASE_URL`` env var or ``database_url`` in config to switch.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
import os

from app.config import settings

# Determine database URL — priority: config > env > default SQLite
_configured_url = settings.database_url or os.getenv("DATABASE_URL", "")
DATABASE_URL = _configured_url if _configured_url else "sqlite+aiosqlite:///./voxdoc.db"

# Engine kwargs differ by backend
_engine_kwargs: dict = {"echo": False}
if "sqlite" in DATABASE_URL:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif "postgresql" in DATABASE_URL:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
