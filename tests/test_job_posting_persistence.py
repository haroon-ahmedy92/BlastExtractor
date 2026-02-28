from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.job_postings import upsert_job_posting
from app.db.session import create_engine, init_db
from app.models.job_posting import JobPosting
from app.models.jobs import JobRecord


def test_job_posting_upsert_insert_update_and_dedupe(tmp_path) -> None:
    async def scenario() -> None:
        database_url = f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}"
        engine = create_engine(database_url)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        try:
            await init_db(bind=engine)
            now = datetime.now(UTC)
            record = JobRecord(
                source="ajira",
                source_url="https://example.com/job/123",
                title="Software Engineer",
                institution="Example Institution",
                number_of_posts=2,
                deadline_date=date(2026, 3, 15),
                category="IT",
                location="Dar es Salaam",
                description_text="Role description",
                description_html="<p>Role description</p>",
                attachments_json=[{"name": "spec.pdf"}],
                content_hash="hash-v1",
            )

            async with session_factory() as session:
                first, result = await upsert_job_posting(session, record)
                await session.commit()
                assert result.action == "inserted"
                first_id = first.id
                first_seen = first.first_seen

            updated_record = record.model_copy(
                update={
                    "title": "Senior Software Engineer",
                    "content_hash": "hash-v2",
                }
            )
            async with session_factory() as session:
                second, result = await upsert_job_posting(session, updated_record)
                await session.commit()
                assert result.action == "updated"
                assert second.id == first_id
                assert second.title == "Senior Software Engineer"
                assert second.content_hash == "hash-v2"
                assert second.first_seen.replace(tzinfo=first_seen.tzinfo) == first_seen
                assert second.last_seen.replace(tzinfo=now.tzinfo) >= first_seen

            async with session_factory() as session:
                third, result = await upsert_job_posting(session, updated_record)
                await session.commit()
                assert result.action == "unchanged"
                total = await session.scalar(
                    select(func.count()).select_from(JobPosting).where(
                        JobPosting.source_url == str(record.source_url)
                    )
                )
                assert total == 1
                assert third.id == first_id
        finally:
            await engine.dispose()

    asyncio.run(scenario())
