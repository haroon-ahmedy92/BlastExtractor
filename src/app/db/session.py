from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base

settings = get_settings()


def create_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(database_url or settings.database_url, echo=False)


engine: AsyncEngine = create_engine()
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db(bind: AsyncEngine | None = None) -> None:
    # Ensure model modules are imported before metadata creation.
    import app.models.job_posting  # noqa: F401

    target_engine = bind or engine
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
