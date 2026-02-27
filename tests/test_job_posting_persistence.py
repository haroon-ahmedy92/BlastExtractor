import asyncio
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.job_postings import JobPostingInput, upsert_job_posting
from app.db.session import create_engine, init_db
from app.models.job_posting import JobPosting


def test_insert_and_dedupe_by_source_url(tmp_path) -> None:
    async def scenario() -> None:
        database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
        engine = create_engine(database_url)
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        try:
            await init_db(bind=engine)

            payload: JobPostingInput = {
                "source": "ajira",
                "source_url": "https://example.com/job/123",
                "title": "Software Engineer",
                "institution": "Example Institution",
                "number_of_posts": 2,
                "deadline_date": date(2026, 3, 15),
                "category": "IT",
                "location": "Dar es Salaam",
                "description_text": "Role description",
                "description_html": "<p>Role description</p>",
                "attachments_json": [{"name": "spec.pdf", "url": "https://example.com/spec.pdf"}],
                "content_hash": "hash-v1",
            }

            async with session_factory() as session:
                first, action = await upsert_job_posting(session, payload)
                await session.commit()
                first_id = first.id
                first_seen = first.first_seen

                assert action == "inserted"
                assert first_id is not None

            updated_payload: JobPostingInput = {
                **payload,
                "title": "Senior Software Engineer",
                "content_hash": "hash-v2",
            }

            async with session_factory() as session:
                second, action = await upsert_job_posting(session, updated_payload)
                await session.commit()

                assert action == "updated"
                assert second.id == first_id

                total = await session.scalar(
                    select(func.count()).select_from(JobPosting).where(
                        JobPosting.source_url == payload["source_url"]
                    )
                )
                assert total == 1
                assert second.title == "Senior Software Engineer"
                assert second.content_hash == "hash-v2"
                assert second.first_seen.replace(tzinfo=first_seen.tzinfo) == first_seen
                normalized_last_seen = second.last_seen.replace(tzinfo=first_seen.tzinfo)
                assert normalized_last_seen >= first_seen

            async with session_factory() as session:
                third, action = await upsert_job_posting(session, updated_payload)
                await session.commit()

                assert action == "unchanged"
                assert third.id == first_id
                assert third.content_hash == "hash-v2"
        finally:
            await engine.dispose()

    asyncio.run(scenario())
