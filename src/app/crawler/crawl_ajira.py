from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.logging import setup_logging
from app.sites.ajira_portal import AjiraPortalSite

logger = logging.getLogger(__name__)


async def run_once() -> None:
    site = AjiraPortalSite()
    listings = await site.fetch_listing_stubs()
    payload = [item.model_dump(mode="json") for item in listings]
    print(json.dumps(payload, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Ajira vacancies")
    parser.add_argument("--once", action="store_true", help="Run one crawl iteration and print JSON")
    return parser.parse_args()


async def main() -> None:
    setup_logging()
    args = parse_args()
    if args.once:
        await run_once()
        return
    logger.error("No mode selected. Use --once.")


if __name__ == "__main__":
    asyncio.run(main())
