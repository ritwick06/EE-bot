"""
Async database engine, session factory, and initialization.

Uses SQLAlchemy 2.0 async with asyncpg for PostgreSQL.
Connection pooling is configured for high-concurrency workloads.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ── Async Engine with connection pooling ─────────────────────────────────────
engine = create_async_engine(
    _settings.database_url,
    echo=False,
    pool_size=20,          # Simultaneous connections
    max_overflow=10,       # Burst capacity above pool_size
    pool_timeout=30,       # Wait for a connection before erroring
    pool_recycle=1800,     # Recycle connections every 30 min
    pool_pre_ping=True,    # Verify connections are alive before use
)

# ── Session Factory ──────────────────────────────────────────────────────────
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional async session scope."""
    session = async_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Create all tables if they do not exist."""
    from models import Base  # Import here to avoid circular imports

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized successfully.")


async def close_db() -> None:
    """Dispose the engine and release all pooled connections."""
    await engine.dispose()
    logger.info("Database engine disposed.")
