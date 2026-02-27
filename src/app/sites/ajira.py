import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
async def fetch_html() -> str:
    settings = get_settings()
    timeout = httpx.Timeout(settings.crawler_timeout_seconds)
    headers = {"User-Agent": "BlastExtractor/0.1"}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        response = await client.get(settings.ajira_url)
        response.raise_for_status()
        logger.info("Fetched Ajira page", extra={"url": settings.ajira_url})
        return response.text
