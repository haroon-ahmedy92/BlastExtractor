"""Legacy Ajira crawl helpers for quick smoke tests.

This module offers a simple HTTP fetch path and a Playwright fallback that
read the Ajira home page title. It is separate from the generic adapter-driven
crawl flow, but remains useful for low-level connectivity checks.
"""

import asyncio
import logging

from lxml import html

from app.logging import setup_logging
from app.sites.ajira import fetch_html

logger = logging.getLogger(__name__)


def extract_title(page_html: str) -> str:
    """Extract the HTML document title.

    Args:
        page_html: Raw HTML document.

    Returns:
        str: Page title or ``"N/A"`` when missing.
    """

    tree = html.fromstring(page_html)
    title = tree.xpath("string(//title)").strip()
    return title or "N/A"


async def crawl_with_httpx() -> str:
    """Fetch Ajira over HTTP and return the page title.

    Returns:
        str: Extracted page title.
    """

    page_html = await fetch_html()
    return extract_title(page_html)


async def crawl_with_playwright(url: str) -> str:
    """Fetch a page title with Playwright.

    Args:
        url: Page URL to open.

    Returns:
        str: Browser-reported title.
    """

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        await browser.close()
        return title


async def main() -> None:
    """Run a simple Ajira connectivity crawl.

    Returns:
        None
    """

    setup_logging()
    from app.config import get_settings

    settings = get_settings()

    try:
        title = await crawl_with_httpx()
        logger.info("Ajira crawl completed", extra={"method": "httpx", "title": title})
    except Exception as error:
        logger.warning("HTTP crawl failed, falling back to Playwright", extra={"error": str(error)})
        title = await crawl_with_playwright(settings.ajira_url)
        logger.info("Ajira crawl completed", extra={"method": "playwright", "title": title})


if __name__ == "__main__":
    asyncio.run(main())
