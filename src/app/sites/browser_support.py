"""Shared browser-driven helper base for site adapters.

This module provides a small reusable layer on top of :class:`SiteAdapter`
for sites that need Playwright navigation, polite rate limiting, retry logic,
and blocked-request classification.
"""

from __future__ import annotations

from asyncio import Lock, sleep
from contextlib import suppress
from time import monotonic
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings
from app.models.common import BaseRecord, BaseStub
from app.sites.base import SiteAdapter

StubT = TypeVar("StubT", bound=BaseStub)
RecordT = TypeVar("RecordT", bound=BaseRecord)


class TransientBrowserError(RuntimeError):
    """Retryable browser or navigation error."""


class BlockedNavigationError(RuntimeError):
    """Raised when a target site blocks navigation."""

    def __init__(self, *, url: str, status_code: int | None, detail: str) -> None:
        super().__init__(detail)
        self.url = url
        self.status_code = status_code
        self.detail = detail


class BrowserSiteAdapter(SiteAdapter[StubT, RecordT]):
    """Site adapter base with shared Playwright navigation helpers."""

    blocked_status_codes = {401, 403, 429}

    def __init__(
        self,
        *,
        browser_context: Any | None,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Store shared browser settings and rate limiting state.

        Args:
            browser_context: Shared Playwright browser context.
            session_factory: Async SQLAlchemy session factory.
        """

        super().__init__(browser_context=browser_context, session_factory=session_factory)
        self.settings: Settings = get_settings()
        self._rate_lock = Lock()
        self._last_request_started = 0.0

    async def _wait_for_rate_limit(self) -> None:
        """Pause if needed to respect the configured per-request delay."""

        async with self._rate_lock:
            current_time = monotonic()
            delay = self.settings.browser_rate_limit_seconds - (
                current_time - self._last_request_started
            )
            if delay > 0:
                await sleep(delay)
            self._last_request_started = monotonic()

    def _classify_navigation_error(self, error: Exception) -> type[Exception]:
        """Map navigation exceptions to retryable or terminal categories.

        Args:
            error: Exception raised while navigating.

        Returns:
            type[Exception]: Error class that should be raised.
        """

        message = str(error).lower()
        transient_markers = ("timeout", "timed out", "net::err", "502", "503", "500")
        if any(marker in message for marker in transient_markers):
            return TransientBrowserError
        return RuntimeError

    async def _fetch_page(
        self,
        url: str,
        *,
        wait_selector: str | None = None,
    ) -> tuple[int | None, str]:
        """Fetch a page with Playwright and return status plus HTML.

        Args:
            url: URL to fetch.
            wait_selector: Optional selector to wait for after navigation.

        Returns:
            tuple[int | None, str]: HTTP-like status code and page HTML.
        """

        if self.browser_context is None:
            raise RuntimeError("Browser context is required for browser-backed adapters")

        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(TransientBrowserError),
        ):
            with attempt:
                page = await self.browser_context.new_page()
                try:
                    await self._wait_for_rate_limit()
                    response = await page.goto(url, wait_until="domcontentloaded")
                    status_code = response.status if response is not None else None
                    if status_code in self.blocked_status_codes:
                        raise BlockedNavigationError(
                            url=url,
                            status_code=status_code,
                            detail=f"Blocked navigation to {url}",
                        )
                    if wait_selector:
                        await page.wait_for_selector(wait_selector, state="attached")
                    else:
                        # Some sites never settle fully; DOM content is often enough for parsing.
                        with suppress(Exception):
                            await page.wait_for_load_state("networkidle", timeout=8_000)
                    return status_code, str(await page.content())
                except BlockedNavigationError:
                    raise
                except Exception as error:
                    error_type = self._classify_navigation_error(error)
                    raise error_type(str(error)) from error
                finally:
                    with suppress(Exception):
                        await page.close()
        raise TransientBrowserError(f"Failed to fetch page: {url}")

    async def _fetch_page_html(self, url: str, *, wait_selector: str | None = None) -> str:
        """Fetch a page and return only the HTML body.

        Args:
            url: URL to fetch.
            wait_selector: Optional selector to wait for after navigation.

        Returns:
            str: Page HTML.
        """

        _, page_html = await self._fetch_page(url, wait_selector=wait_selector)
        return page_html

    def _log_blocked(self, *, url: str, status_code: int | None, detail: str) -> None:
        """Emit a structured log event for a blocked navigation.

        Args:
            url: Target URL.
            status_code: Response status if known.
            detail: Human-readable evidence string.
        """

        self.logger.warning(
            "blocked",
            extra={
                "site_name": self.site_name,
                "url": url,
                "status_code": status_code,
                "detail": detail,
            },
        )
