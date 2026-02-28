"""HTTP-only helper for fetching the Ajira landing page.

This module is used by the legacy smoke-test crawler in ``app.crawler.ajira``.
It is separate from the main adapter-based crawl flow, which lives in
``app.sites.ajira_portal``.
"""

import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
async def fetch_html() -> str:
    """Fetch the Ajira landing page HTML with retries.

    Returns:
        str: Raw HTML response body.
    """

    settings = get_settings()
    timeout = httpx.Timeout(settings.crawler_timeout_seconds)
    headers = {"User-Agent": "BlastExtractor/0.1"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as http_client:
        response = await http_client.get(settings.ajira_url)
        response.raise_for_status()
        logger.info("Fetched Ajira page", extra={"url": settings.ajira_url})
        return response.text
