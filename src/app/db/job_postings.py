"""Persistence helpers for job posting records.

Adapters that emit :class:`app.models.jobs.JobRecord` call
:func:`upsert_job_posting` near the end of the crawl flow. The function dedupes
by ``source_url``, updates ``last_seen``, and only rewrites content fields when
the ``content_hash`` changes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import UpsertAction, UpsertResult
from app.models.job_posting import JobPosting
from app.models.jobs import JobRecord


async def upsert_job_posting(
    session: AsyncSession,
    record: JobRecord,
) -> tuple[JobPosting, UpsertResult]:
    """Insert or update a job posting row.

    Args:
        session: Active database session.
        record: Normalized job record from an adapter.

    Returns:
        tuple[JobPosting, UpsertResult]: Stored ORM row and action summary.
    """

    query_result = await session.execute(
        select(JobPosting).where(JobPosting.source_url == str(record.source_url))
    )
    existing_posting = query_result.scalar_one_or_none()
    current_time = datetime.now(UTC)

    if existing_posting is not None:
        existing_posting.last_seen = current_time
        existing_posting.source = record.source
        action: UpsertAction = "unchanged"
        if existing_posting.content_hash != record.content_hash:
            existing_posting.title = record.title
            existing_posting.institution = record.institution
            existing_posting.number_of_posts = record.number_of_posts
            existing_posting.deadline_date = record.deadline_date
            existing_posting.category = record.category
            existing_posting.location = record.location
            existing_posting.description_text = record.description_text
            existing_posting.description_html = record.description_html
            existing_posting.attachments_json = record.attachments_json
            existing_posting.content_hash = record.content_hash
            action = "updated"
        await session.flush()
        return existing_posting, UpsertResult(action=action, record_id=existing_posting.id)

    new_posting = JobPosting(
        source=record.source,
        source_url=str(record.source_url),
        title=record.title,
        institution=record.institution,
        number_of_posts=record.number_of_posts,
        deadline_date=record.deadline_date,
        category=record.category,
        location=record.location,
        description_text=record.description_text,
        description_html=record.description_html,
        attachments_json=record.attachments_json,
        content_hash=record.content_hash,
        first_seen=current_time,
        last_seen=current_time,
    )
    session.add(new_posting)
    await session.flush()
    return new_posting, UpsertResult(action="inserted", record_id=new_posting.id)
