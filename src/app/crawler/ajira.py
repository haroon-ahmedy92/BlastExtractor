import asyncio
import logging

from lxml import html

from app.logging import setup_logging
from app.sites.ajira import fetch_html

logger = logging.getLogger(__name__)


def extract_title(page_html: str) -> str:
    tree = html.fromstring(page_html)
    title = tree.xpath("string(//title)").strip()
    return title or "N/A"


async def crawl_with_httpx() -> str:
    page_html = await fetch_html()
    return extract_title(page_html)


async def crawl_with_playwright(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        title = await page.title()
        await browser.close()
        return title


async def main() -> None:
    setup_logging()
    from app.config import get_settings

    settings = get_settings()

    try:
        title = await crawl_with_httpx()
        logger.info("Ajira crawl completed", extra={"method": "httpx", "title": title})
    except Exception as exc:
        logger.warning("HTTP crawl failed, falling back to Playwright", extra={"error": str(exc)})
        title = await crawl_with_playwright(settings.ajira_url)
        logger.info("Ajira crawl completed", extra={"method": "playwright", "title": title})


if __name__ == "__main__":
    asyncio.run(main())
