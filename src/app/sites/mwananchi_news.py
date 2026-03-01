"""Mwananchi news adapter with graceful blocked-site handling."""

from __future__ import annotations

from app.db.news_articles import upsert_news_article
from app.models.common import ContentType, UpsertResult
from app.models.news import NewsRecord, NewsStub
from app.sites.browser_support import BlockedNavigationError, BrowserSiteAdapter
from app.sites.nation_media_support import discover_news_stubs, parse_news_record
from app.sites.registry import register_adapter

MWANANCHI_HOME_URL = "https://www.mwananchi.co.tz/"


class MwananchiNewsAdapter(BrowserSiteAdapter[NewsStub, NewsRecord]):
    """News adapter for Mwananchi homepage stories."""

    site_name = "mwananchi_news"
    content_type = ContentType.NEWS

    async def discover(self) -> list[NewsStub]:
        """Discover article links from Mwananchi homepage content."""

        if not self.settings.mwananchi_enabled:
            self.logger.info(
                "Skipping disabled site",
                extra={"site_name": self.site_name, "detail": "MWANANCHI_ENABLED=false"},
            )
            return []
        try:
            _, page_html = await self._fetch_page(MWANANCHI_HOME_URL, wait_selector="a[href]")
        except BlockedNavigationError as error:
            self._log_blocked(
                url=error.url,
                status_code=error.status_code,
                detail=error.detail,
            )
            return []
        except Exception as error:
            self._log_blocked(url=MWANANCHI_HOME_URL, status_code=None, detail=str(error))
            return []

        return discover_news_stubs(
            page_html,
            base_url=MWANANCHI_HOME_URL,
            source_name=self.site_name,
            allowed_prefixes=("/mw/habari/",),
            excluded_prefixes=("/mw/katuni/",),
        )

    async def fetch_details(self, stub: NewsStub) -> NewsRecord:
        """Fetch and parse one Mwananchi article."""

        try:
            page_html = await self._fetch_page_html(str(stub.url), wait_selector="h1")
        except BlockedNavigationError as error:
            self._log_blocked(
                url=error.url,
                status_code=error.status_code,
                detail=error.detail,
            )
            raise
        except Exception as error:
            self._log_blocked(url=str(stub.url), status_code=None, detail=str(error))
            raise
        return parse_news_record(
            page_html,
            source=self.site_name,
            source_url=str(stub.url),
            fallback_title=stub.title,
        )

    async def upsert(self, record: NewsRecord) -> UpsertResult:
        """Persist one Mwananchi article into the news table."""

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_news_article(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("mwananchi_news", MwananchiNewsAdapter)
