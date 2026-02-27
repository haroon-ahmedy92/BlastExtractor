from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.db.job_postings import JobPostingInput, upsert_job_posting
from app.db.session import SessionLocal, init_db
from app.logging import setup_logging
from app.sites.ajira_portal import AjiraPortalSite

logger = logging.getLogger(__name__)


async def run_once() -> None:
    site = AjiraPortalSite()
    listings = await site.crawl_with_details(max_concurrency=4)
    discovered = len(listings)

    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    await init_db()
    async with SessionLocal() as session:
        for item in listings:
            metadata = item.extra_metadata or {}
            category = metadata.get("category") or metadata.get("job category")
            location = metadata.get("duty station") or metadata.get("location")
            attachments_json = None
            if item.attachments or metadata:
                attachments_json = {"links": item.attachments or [], "metadata": metadata}

            payload: JobPostingInput = {
                "source": "ajira_portal",
                "source_url": str(item.details_url),
                "title": item.title,
                "institution": item.institution or "Unknown",
                "content_hash": item.content_hash,
                "number_of_posts": item.number_of_posts,
                "deadline_date": item.deadline_date,
                "category": category,
                "location": location,
                "description_text": item.description_text,
                "description_html": item.description_html,
                "attachments_json": attachments_json,
            }
            _, action = await upsert_job_posting(session, payload)
            counts[action] += 1

        await session.commit()

    logger.info(
        "Ajira sync summary",
        extra={
            "discovered": discovered,
            "inserted": counts["inserted"],
            "updated": counts["updated"],
            "unchanged": counts["unchanged"],
        },
    )

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
