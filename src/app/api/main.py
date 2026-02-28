"""FastAPI application for reading stored job postings.

This module defines the API lifespan hook, response models, and job endpoints.
It sits after the crawl flow: adapters store normalized records in the
database, and these handlers query those rows for external clients.
"""

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
    """Initialize database tables when the API starts.

    Args:
        _: FastAPI application instance, unused by the lifespan hook.

    Yields:
        None: Control back to FastAPI while the app is running.
    """

    await init_db()
    yield


class HealthResponse(BaseModel):
    """Response model for the health endpoint."""

    status: str
    service: str


class JobPostingResponse(BaseModel):
    """Serialized job posting returned by the API."""

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
    """Paginated job listing response."""

    total: int
    limit: int
    offset: int
    items: list[JobPostingResponse]


app = FastAPI(title=settings.app_name, lifespan=lifespan)
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def _normalize_source_filter(source: str | None) -> list[str] | None:
    """Map external source names to stored source values.

    Args:
        source: Raw query parameter from the request.

    Returns:
        list[str] | None: Matching stored source names, or ``None`` for no
        source filter.
    """

    if source is None:
        return None
    normalized = source.strip().lower()
    if normalized == "ajira":
        return ["ajira", "ajira_portal"]
    return [normalized]


def _build_jobs_query(
    *,
    source: str | None,
    query: str | None,
    category: str | None,
    deadline_from: date | None,
    deadline_to: date | None,
) -> Select[tuple[JobPosting]]:
    """Build the filtered SQL query for job listings.

    Args:
        source: Optional source filter.
        query: Optional free-text search value.
        category: Optional category filter.
        deadline_from: Optional lower deadline bound.
        deadline_to: Optional upper deadline bound.

    Returns:
        Select[tuple[JobPosting]]: SQLAlchemy query for matching jobs.
    """

    query_stmt = select(JobPosting)
    normalized_sources = _normalize_source_filter(source)
    if normalized_sources:
        query_stmt = query_stmt.where(JobPosting.source.in_(normalized_sources))
    if query:
        pattern = f"%{query.strip()}%"
        query_stmt = query_stmt.where(
            or_(
                JobPosting.title.ilike(pattern),
                JobPosting.institution.ilike(pattern),
                JobPosting.description_text.ilike(pattern),
            )
        )
    if category:
        query_stmt = query_stmt.where(JobPosting.category.ilike(f"%{category.strip()}%"))
    if deadline_from:
        query_stmt = query_stmt.where(JobPosting.deadline_date >= deadline_from)
    if deadline_to:
        query_stmt = query_stmt.where(JobPosting.deadline_date <= deadline_to)

    return query_stmt.order_by(JobPosting.deadline_date.asc(), JobPosting.id.desc())


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return a basic service health response.

    Returns:
        HealthResponse: Static status payload.
    """

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
    """List stored jobs with simple filters and pagination.

    Args:
        session: Database session dependency.
        source: Optional source filter.
        query: Optional free-text search value.
        category: Optional category filter.
        deadline_from: Optional lower deadline bound.
        deadline_to: Optional upper deadline bound.
        limit: Maximum number of records to return.
        offset: Number of records to skip.

    Returns:
        JobPostingListResponse: Paginated job results.
    """

    query_stmt = _build_jobs_query(
        source=source,
        query=query,
        category=category,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
    )
    count_stmt = select(func.count()).select_from(query_stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    result = await session.execute(query_stmt.limit(limit).offset(offset))
    items = [JobPostingResponse.model_validate(job_row) for job_row in result.scalars().all()]
    return JobPostingListResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/jobs/{job_id}", response_model=JobPostingResponse)
async def get_job(
    job_id: int,
    session: DbSession,
) -> JobPostingResponse:
    """Fetch one stored job by primary key.

    Args:
        job_id: Database identifier for the job.
        session: Database session dependency.

    Returns:
        JobPostingResponse: Serialized job posting.

    Raises:
        HTTPException: If the job does not exist.
    """

    job_posting = await session.get(JobPosting, job_id)
    if job_posting is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobPostingResponse.model_validate(job_posting)
