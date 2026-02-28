"""Placeholder news adapter used to prove the plugin system works.

This adapter intentionally discovers nothing and performs no real scraping. It
exists so the generic crawl runner can demonstrate a news-type adapter without
depending on a live website.
"""

from __future__ import annotations

from app.db.news_articles import upsert_news_article
from app.models.common import ContentType, UpsertResult
from app.models.news import NewsRecord, NewsStub
from app.sites.base import SiteAdapter
from app.sites.registry import register_adapter


class GenericNewsStubAdapter(SiteAdapter[NewsStub, NewsRecord]):
    """No-op news adapter for plugin architecture smoke tests."""

    site_name = "news_stub"
    content_type = ContentType.NEWS
    requires_browser = False

    async def discover(self) -> list[NewsStub]:
        """Return no discovered news items.

        Returns:
            list[NewsStub]: Always an empty list.
        """

        self.logger.info("No-op news adapter discover", extra={"site_name": self.site_name})
        return []

    async def fetch_details(self, stub: NewsStub) -> NewsRecord:
        """Raise because this placeholder adapter has no detail fetch step.

        Args:
            stub: Discovered stub that should never exist here.

        Returns:
            NewsRecord: Never returns.
        """

        raise RuntimeError(f"{self.site_name} has no detail fetch implementation for {stub.url}")

    async def upsert(self, record: NewsRecord) -> UpsertResult:
        """Persist a news record if one is supplied.

        Args:
            record: Normalized news record.

        Returns:
            UpsertResult: Summary of the database action taken.
        """

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_news_article(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("news_stub", GenericNewsStubAdapter)
