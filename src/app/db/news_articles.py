"""Persistence helpers for news article records.

News adapters use :func:`upsert_news_article` to dedupe records by
``source_url`` and to track whether a page is new, changed, or unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import UpsertAction, UpsertResult
from app.models.news import NewsRecord
from app.models.news_article import NewsArticle


async def upsert_news_article(
    session: AsyncSession,
    record: NewsRecord,
) -> tuple[NewsArticle, UpsertResult]:
    """Insert or update a news article row.

    Args:
        session: Active database session.
        record: Normalized news record from an adapter.

    Returns:
        tuple[NewsArticle, UpsertResult]: Stored ORM row and action summary.
    """

    query_result = await session.execute(
        select(NewsArticle).where(NewsArticle.source_url == str(record.source_url))
    )
    existing_article = query_result.scalar_one_or_none()
    current_time = datetime.now(UTC)

    if existing_article is not None:
        existing_article.last_seen = current_time
        existing_article.source = record.source
        action: UpsertAction = "unchanged"
        if existing_article.content_hash != record.content_hash:
            existing_article.title = record.title
            existing_article.author = record.author
            existing_article.published_at = record.published_at
            existing_article.section = record.section
            existing_article.body_text = record.body_text
            existing_article.body_html = record.body_html
            existing_article.tags_json = record.tags_json
            existing_article.attachments_json = record.attachments_json
            existing_article.content_hash = record.content_hash
            action = "updated"
        await session.flush()
        return existing_article, UpsertResult(action=action, record_id=existing_article.id)

    new_article = NewsArticle(
        source=record.source,
        source_url=str(record.source_url),
        title=record.title,
        author=record.author,
        published_at=record.published_at,
        section=record.section,
        body_text=record.body_text,
        body_html=record.body_html,
        tags_json=record.tags_json,
        attachments_json=record.attachments_json,
        content_hash=record.content_hash,
        first_seen=current_time,
        last_seen=current_time,
    )
    session.add(new_article)
    await session.flush()
    return new_article, UpsertResult(action="inserted", record_id=new_article.id)
