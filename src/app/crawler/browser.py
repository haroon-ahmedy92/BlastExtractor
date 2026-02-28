"""Shared Playwright browser context for crawl runs.

The generic crawler runner uses this module to open one browser and one
context per crawl run. Adapters receive the context so they can fetch pages
without launching browsers repeatedly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import get_settings


@asynccontextmanager
async def browser_context() -> AsyncIterator[object]:
    """Create a performance-friendly Playwright browser context.

    Yields:
        AsyncIterator[object]: Shared Playwright browser context for adapters.
    """

    from playwright.async_api import async_playwright

    settings = get_settings()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=settings.browser_headless,
            args=["--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = await browser.new_context(ignore_https_errors=True)

        async def block_unneeded_resources(route, request) -> None:
            # Large assets rarely affect the text extraction we care about.
            if request.resource_type in {"font", "image", "media"}:
                await route.abort()
                return
            await route.continue_()

        await context.route("**/*", block_unneeded_resources)
        context.set_default_timeout(settings.browser_timeout_ms)
        context.set_default_navigation_timeout(settings.browser_timeout_ms)
        try:
            yield context
        finally:
            await context.close()
            await browser.close()
