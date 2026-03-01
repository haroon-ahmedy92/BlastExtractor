"""The Citizen news adapter."""

from __future__ import annotations

from app.db.news_articles import upsert_news_article
from app.models.common import ContentType, UpsertResult
from app.models.news import NewsRecord, NewsStub
from app.sites.browser_support import BrowserSiteAdapter
from app.sites.nation_media_support import discover_news_stubs, parse_news_record
from app.sites.registry import register_adapter

CITIZEN_NEWS_URL = "https://www.thecitizen.co.tz/tanzania/news"


class TheCitizenNewsAdapter(BrowserSiteAdapter[NewsStub, NewsRecord]):
    """News adapter for The Citizen Tanzania section."""

    site_name = "citizen_news"
    content_type = ContentType.NEWS

    async def discover(self) -> list[NewsStub]:
        """Discover article links from The Citizen news listing page."""

        page_html = await self._fetch_page_html(
            CITIZEN_NEWS_URL,
            wait_selector="a[href*='/tanzania/news/']",
        )
        return discover_news_stubs(
            page_html,
            base_url=CITIZEN_NEWS_URL,
            source_name=self.site_name,
            allowed_prefixes=("/tanzania/news/",),
        )

    async def fetch_details(self, stub: NewsStub) -> NewsRecord:
        """Fetch and parse one Citizen article."""

        page_html = await self._fetch_page_html(str(stub.url), wait_selector="h1")
        return parse_news_record(
            page_html,
            source=self.site_name,
            source_url=str(stub.url),
            fallback_title=stub.title,
        )

    async def upsert(self, record: NewsRecord) -> UpsertResult:
        """Persist one Citizen article into the news table."""

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_news_article(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("citizen_news", TheCitizenNewsAdapter)
