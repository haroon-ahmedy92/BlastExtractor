from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.main import app
from app.db.base import Base
from app.db.session import get_db_session
from app.models.job_posting import JobPosting


@pytest.fixture
async def api_session() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture
async def api_client(api_session: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with api_session() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=cast(Any, app))
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()


async def _seed_jobs(session_factory: async_sessionmaker[AsyncSession]) -> None:
    now = datetime.now(UTC)
    jobs = [
        JobPosting(
            source="ajira_portal",
            source_url="https://example.com/jobs/1",
            title="Data Engineer",
            institution="Public Data Agency",
            number_of_posts=2,
            deadline_date=date(2026, 3, 10),
            category="Engineering",
            location="Dodoma",
            description_text="Build reliable data pipelines",
            description_html="<p>Build reliable data pipelines</p>",
            attachments_json={"links": []},
            content_hash="hash-1",
            first_seen=now,
            last_seen=now,
        ),
        JobPosting(
            source="ajira_portal",
            source_url="https://example.com/jobs/2",
            title="Policy Analyst",
            institution="Civil Service Unit",
            number_of_posts=1,
            deadline_date=date(2026, 4, 15),
            category="Policy",
            location="Dar es Salaam",
            description_text="Analyse policy submissions",
            description_html="<p>Analyse policy submissions</p>",
            attachments_json=None,
            content_hash="hash-2",
            first_seen=now,
            last_seen=now,
        ),
        JobPosting(
            source="other_source",
            source_url="https://example.com/jobs/3",
            title="Field Officer",
            institution="Regional Office",
            number_of_posts=3,
            deadline_date=date(2026, 2, 28),
            category="Operations",
            location="Arusha",
            description_text="Support field operations",
            description_html="<p>Support field operations</p>",
            attachments_json=None,
            content_hash="hash-3",
            first_seen=now,
            last_seen=now,
        ),
    ]

    async with session_factory() as session:
        session.add_all(jobs)
        await session.commit()


@pytest.mark.asyncio
async def test_health_endpoint(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_jobs_supports_filters_and_pagination(
    api_client: AsyncClient, api_session: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_jobs(api_session)

    response = await api_client.get(
        "/jobs",
        params={
            "source": "ajira",
            "query": "data",
            "category": "engine",
            "deadline_from": "2026-03-01",
            "deadline_to": "2026-03-31",
            "limit": 1,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "Data Engineer"
    assert payload["items"][0]["source"] == "ajira_portal"


@pytest.mark.asyncio
async def test_get_job_by_id_returns_full_record(
    api_client: AsyncClient, api_session: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_jobs(api_session)

    response = await api_client.get("/jobs/2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 2
    assert payload["title"] == "Policy Analyst"
    assert payload["category"] == "Policy"


@pytest.mark.asyncio
async def test_get_job_by_id_returns_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/jobs/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}
