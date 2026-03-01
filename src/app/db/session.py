"""Database engine, sessions, and table initialization helpers.

This module creates the shared async SQLAlchemy engine and session factory used
by adapters and the API. During the crawl flow, adapters use
``SessionLocal`` inside their ``upsert`` methods to write records.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
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

ADDITIVE_SCHEMA_UPDATES: dict[str, dict[str, str]] = {
    "news_articles": {
        "section": "VARCHAR(255) NULL",
    },
    "exam_results": {
        "centre_code": "VARCHAR(120) NULL",
        "centre_name": "VARCHAR(255) NULL",
    },
}

MYSQL_COLUMN_TYPE_UPDATES: dict[str, dict[str, str]] = {
    "job_postings": {
        "category": "LONGTEXT NULL",
        "description_text": "LONGTEXT NULL",
        "description_html": "LONGTEXT NULL",
    },
    "news_articles": {
        "body_text": "LONGTEXT NULL",
        "body_html": "LONGTEXT NULL",
    },
}


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield an async database session for FastAPI dependencies.

    Yields:
        AsyncIterator[AsyncSession]: Active database session.
    """

    async with SessionLocal() as db_session:
        yield db_session


def _sync_additive_columns(connection: Connection) -> None:
    """Add a small set of known-safe missing columns to existing tables.

    Args:
        connection: Synchronous SQLAlchemy connection inside ``run_sync``.

    Returns:
        None
    """

    inspector = inspect(connection)
    for table_name, columns in ADDITIVE_SCHEMA_UPDATES.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column_sql in columns.items():
            if column_name in existing_columns:
                continue
            ddl = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
            connection.execute(text(ddl))


def _sync_mysql_column_types(connection: Connection) -> None:
    """Upgrade a small set of existing MySQL columns to safer text sizes.

    Args:
        connection: Synchronous SQLAlchemy connection inside ``run_sync``.

    Returns:
        None
    """

    if connection.dialect.name != "mysql":
        return

    inspector = inspect(connection)
    for table_name, columns in MYSQL_COLUMN_TYPE_UPDATES.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column_sql in columns.items():
            if column_name not in existing_columns:
                continue
            ddl = f"ALTER TABLE {table_name} MODIFY COLUMN {column_name} {column_sql}"
            connection.execute(text(ddl))


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
        await connection.run_sync(_sync_additive_columns)
        await connection.run_sync(_sync_mysql_column_types)
