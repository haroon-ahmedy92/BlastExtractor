"""Database engine, sessions, and table initialization helpers.

This module creates the shared async SQLAlchemy engine and session factory used
by adapters and the API. During the crawl flow, adapters use
``SessionLocal`` inside their ``upsert`` methods to write records.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.base import Base

settings = get_settings()


def create_engine(database_url: str | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: Optional database URL override.

    Returns:
        AsyncEngine: Configured async database engine.
    """

    return create_async_engine(database_url or settings.database_url, echo=False)


engine: AsyncEngine = create_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for FastAPI dependencies.

    Yields:
        AsyncIterator[AsyncSession]: Active database session.
    """

    async with SessionLocal() as db_session:
        yield db_session


async def init_db(bind: AsyncEngine | None = None) -> None:
    """Create all registered database tables.

    Args:
        bind: Optional engine override, mainly useful in tests.

    Returns:
        None
    """

    import app.models.exam_result  # noqa: F401
    import app.models.job_posting  # noqa: F401
    import app.models.news_article  # noqa: F401

    target_engine = bind or engine
    async with target_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
