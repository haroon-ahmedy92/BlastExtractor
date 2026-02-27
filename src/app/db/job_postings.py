from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_posting import JobPosting


class JobPostingInput(TypedDict):
    source: str
    source_url: str
    title: str
    institution: str
    content_hash: str
    number_of_posts: int | None
    deadline_date: date | None
    category: str | None
    location: str | None
    description_text: str | None
    description_html: str | None
    attachments_json: dict[str, Any] | list[Any] | None


async def upsert_job_posting(
    session: AsyncSession, payload: JobPostingInput
) -> tuple[JobPosting, bool]:
    result = await session.execute(
        select(JobPosting).where(JobPosting.source_url == payload["source_url"])
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(UTC)

    if existing is not None:
        existing.source = payload["source"]
        existing.title = payload["title"]
        existing.institution = payload["institution"]
        existing.number_of_posts = payload["number_of_posts"]
        existing.deadline_date = payload["deadline_date"]
        existing.category = payload["category"]
        existing.location = payload["location"]
        existing.description_text = payload["description_text"]
        existing.description_html = payload["description_html"]
        existing.attachments_json = payload["attachments_json"]
        existing.content_hash = payload["content_hash"]
        existing.last_seen = now
        await session.flush()
        return existing, False

    posting = JobPosting(
        source=payload["source"],
        source_url=payload["source_url"],
        title=payload["title"],
        institution=payload["institution"],
        number_of_posts=payload["number_of_posts"],
        deadline_date=payload["deadline_date"],
        category=payload["category"],
        location=payload["location"],
        description_text=payload["description_text"],
        description_html=payload["description_html"],
        attachments_json=payload["attachments_json"],
        content_hash=payload["content_hash"],
        first_seen=now,
        last_seen=now,
    )
    session.add(posting)
    await session.flush()
    return posting, True
