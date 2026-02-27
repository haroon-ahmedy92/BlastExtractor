from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db_session, init_db
from app.logging import setup_logging
from app.models.job_posting import JobPosting

setup_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


class HealthResponse(BaseModel):
    status: str
    service: str


class JobPostingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_url: str
    title: str
    institution: str
    number_of_posts: int | None
    deadline_date: date | None
    category: str | None
    location: str | None
    description_text: str | None
    description_html: str | None
    attachments_json: dict[str, Any] | list[Any] | None
    content_hash: str
    first_seen: datetime
    last_seen: datetime


class JobPostingListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobPostingResponse]


app = FastAPI(title=settings.app_name, lifespan=lifespan)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def _normalize_source_filter(source: str | None) -> str | None:
    if source is None:
        return None
    normalized = source.strip().lower()
    source_aliases = {
        "ajira": "ajira_portal",
        "ajira_portal": "ajira_portal",
    }
    return source_aliases.get(normalized, normalized)


def _build_jobs_query(
    *,
    source: str | None,
    query: str | None,
    category: str | None,
    deadline_from: date | None,
    deadline_to: date | None,
) -> Select[tuple[JobPosting]]:
    stmt = select(JobPosting)
    normalized_source = _normalize_source_filter(source)

    if normalized_source:
        stmt = stmt.where(JobPosting.source == normalized_source)
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                JobPosting.title.ilike(pattern),
                JobPosting.institution.ilike(pattern),
                JobPosting.description_text.ilike(pattern),
            )
        )
    if category:
        stmt = stmt.where(JobPosting.category.ilike(f"%{category.strip()}%"))
    if deadline_from:
        stmt = stmt.where(JobPosting.deadline_date >= deadline_from)
    if deadline_to:
        stmt = stmt.where(JobPosting.deadline_date <= deadline_to)

    return stmt.order_by(JobPosting.deadline_date.asc(), JobPosting.id.desc())


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@app.get("/jobs", response_model=JobPostingListResponse)
async def list_jobs(
    session: DbSession,
    source: str | None = None,
    query: str | None = None,
    category: str | None = None,
    deadline_from: date | None = None,
    deadline_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobPostingListResponse:
    stmt = _build_jobs_query(
        source=source,
        query=query,
        category=category,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(total_stmt)).scalar_one())
    result = await session.execute(stmt.limit(limit).offset(offset))
    items = [JobPostingResponse.model_validate(job) for job in result.scalars().all()]
    return JobPostingListResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/jobs/{job_id}", response_model=JobPostingResponse)
async def get_job(
    job_id: int,
    session: DbSession,
) -> JobPostingResponse:
    job = await session.get(JobPosting, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobPostingResponse.model_validate(job)
