from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.exam_results import upsert_exam_result
from app.db.news_articles import upsert_news_article
from app.db.session import create_engine, init_db
from app.models.exam_result import ExamResult
from app.models.exams import ExamRecord
from app.models.news import NewsRecord
from app.models.news_article import NewsArticle


def test_news_article_upsert_behaviour(tmp_path) -> None:
    async def scenario() -> None:
        engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'news.db'}")
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            await init_db(bind=engine)
            record = NewsRecord(
                source="news_stub",
                source_url="https://example.com/news/1",
                title="Breaking News",
                author="Reporter",
                published_at=datetime.now(UTC),
                section="National",
                body_text="Important body",
                body_html="<p>Important body</p>",
                tags_json=["news"],
                attachments_json=None,
                content_hash="hash-1",
            )
            async with session_factory() as session:
                first, result = await upsert_news_article(session, record)
                await session.commit()
                assert result.action == "inserted"
                first_id = first.id

            updated = record.model_copy(
                update={"body_text": "Updated body", "content_hash": "hash-2"}
            )
            async with session_factory() as session:
                second, result = await upsert_news_article(session, updated)
                await session.commit()
                assert result.action == "updated"
                assert second.id == first_id

            async with session_factory() as session:
                _, result = await upsert_news_article(session, updated)
                await session.commit()
                total = await session.scalar(
                    select(func.count()).select_from(NewsArticle).where(
                        NewsArticle.source_url == str(record.source_url)
                    )
                )
                assert result.action == "unchanged"
                assert total == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_exam_result_upsert_behaviour(tmp_path) -> None:
    async def scenario() -> None:
        engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'exams.db'}")
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        try:
            await init_db(bind=engine)
            record = ExamRecord(
                source="exam_stub",
                source_url="https://example.com/exams/1",
                title="CSEE 2025",
                year=2025,
                exam_type="CSEE",
                centre_code="S001",
                centre_name="Example School",
                results_json={"Math": "A"},
                content_hash="hash-1",
            )
            async with session_factory() as session:
                first, result = await upsert_exam_result(session, record)
                await session.commit()
                assert result.action == "inserted"
                first_id = first.id

            updated = record.model_copy(
                update={"centre_name": "Updated School", "content_hash": "hash-2"}
            )
            async with session_factory() as session:
                second, result = await upsert_exam_result(session, updated)
                await session.commit()
                assert result.action == "updated"
                assert second.id == first_id

            async with session_factory() as session:
                _, result = await upsert_exam_result(session, updated)
                await session.commit()
                total = await session.scalar(
                    select(func.count()).select_from(ExamResult).where(
                        ExamResult.source_url == str(record.source_url)
                    )
                )
                assert result.action == "unchanged"
                assert total == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())
