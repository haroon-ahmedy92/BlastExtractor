from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.job_postings import JobPostingInput, upsert_job_posting
from app.db.session import SessionLocal, engine, init_db
from app.logging import setup_logging
from app.models.job_posting import JobPosting
from app.models.listing_detail import ListingDetail
from app.models.listing_stub import ListingStub
from app.sites.ajira_portal import AjiraPortalSite, CrawlRunStats

logger = logging.getLogger(__name__)


def export_jsonl(path: str, items: Sequence[ListingDetail]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def print_end_of_run_report(
    *,
    mode: str,
    counts: dict[str, int],
    crawl_stats: CrawlRunStats,
    export_path: str | None = None,
) -> None:
    lines = [
        "",
        "Ajira Crawl Report",
        f"mode: {mode}",
        f"discovered: {counts.get('discovered', 0)}",
        f"refreshed: {counts.get('refreshed', 0)}",
        f"inserted: {counts.get('inserted', 0)}",
        f"updated: {counts.get('updated', 0)}",
        f"unchanged: {counts.get('unchanged', 0)}",
        f"touched: {counts.get('touched', 0)}",
        f"detail_attempted: {crawl_stats.detail_attempted}",
        f"detail_succeeded: {crawl_stats.detail_succeeded}",
        f"detail_failed: {crawl_stats.detail_failed}",
        f"retries: {crawl_stats.retries}",
        f"transient_errors: {crawl_stats.transient_errors}",
        f"permanent_errors: {crawl_stats.permanent_errors}",
        f"blocked_requests: {crawl_stats.blocked_requests}",
        f"rate_limited_waits: {crawl_stats.rate_limited_waits}",
        f"elapsed_seconds: {crawl_stats.elapsed_seconds}",
    ]
    if export_path:
        lines.append(f"export: {export_path}")
    print("\n".join(lines), file=sys.stderr)


def listing_metadata_signature(stub: ListingStub) -> tuple[str, str | None, int | None, str | None]:
    return (
        stub.title,
        stub.institution,
        stub.number_of_posts,
        stub.deadline_date.isoformat() if stub.deadline_date else None,
    )


def posting_metadata_signature(posting: JobPosting) -> tuple[str, str | None, int | None, str | None]:
    return (
        posting.title,
        posting.institution,
        posting.number_of_posts,
        posting.deadline_date.isoformat() if posting.deadline_date else None,
    )


def should_refresh_listing_detail(
    stub: ListingStub,
    existing: JobPosting | None,
    *,
    refresh_after_days: int,
    now: datetime,
) -> bool:
    if existing is None:
        return True
    if listing_metadata_signature(stub) != posting_metadata_signature(existing):
        return True
    refresh_cutoff = now - timedelta(days=refresh_after_days)
    return existing.last_seen <= refresh_cutoff


async def _load_existing_postings(
    session: AsyncSession,
    *,
    source: str,
    source_urls: Sequence[str],
) -> dict[str, JobPosting]:
    if not source_urls:
        return {}
    result = await session.execute(
        select(JobPosting).where(
            JobPosting.source == source,
            JobPosting.source_url.in_(source_urls),
        )
    )
    postings = result.scalars().all()
    return {posting.source_url: posting for posting in postings}


def _build_job_posting_payload(item: ListingDetail) -> JobPostingInput:
    metadata = dict(item.extra_metadata or {})
    structured_fields = dict(item.structured_fields or {})
    if structured_fields:
        metadata["structured_fields"] = structured_fields
    category = metadata.get("category") or metadata.get("job category")
    location = metadata.get("duty station") or metadata.get("location")
    attachments_json = None
    if item.attachments or metadata:
        attachments_json = {"links": item.attachments or [], "metadata": metadata}

    return {
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


async def sync_ajira_incremental(
    *,
    max_concurrency: int = 4,
    refresh_after_days: int = 7,
) -> tuple[dict[str, int], CrawlRunStats]:
    site = AjiraPortalSite()
    crawl_stats = CrawlRunStats()
    counts = {
        "discovered": 0,
        "refreshed": 0,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "touched": 0,
    }
    now = datetime.now(UTC)

    await init_db()
    try:
        async with site.browser_session(crawl_stats) as context:
            stubs = await site.fetch_listing_stubs_from_context(context, stats=crawl_stats)
            counts["discovered"] = len(stubs)

            async with SessionLocal() as session:
                source_urls = [str(stub.details_url) for stub in stubs]
                existing_postings = await _load_existing_postings(
                    session,
                    source="ajira_portal",
                    source_urls=source_urls,
                )
                refresh_candidates = [
                    stub
                    for stub in stubs
                    if should_refresh_listing_detail(
                        stub,
                        existing_postings.get(str(stub.details_url)),
                        refresh_after_days=refresh_after_days,
                        now=now,
                    )
                ]

                refresh_candidate_urls = {str(stub.details_url) for stub in refresh_candidates}
                for posting in existing_postings.values():
                    if posting.source_url in refresh_candidate_urls:
                        continue
                    posting.last_seen = now
                    counts["touched"] += 1

                detailed_items = await site.fetch_listing_details_from_context(
                    context,
                    refresh_candidates,
                    max_concurrency=max_concurrency,
                    stats=crawl_stats,
                )
                counts["refreshed"] = len(detailed_items)

                for item in detailed_items:
                    payload = _build_job_posting_payload(item)
                    _, action = await upsert_job_posting(session, payload)
                    counts[action] += 1

                await session.commit()

        logger.info("Ajira incremental sync summary", extra=counts)
        return counts, crawl_stats
    finally:
        await engine.dispose()


async def run_once(*, export_path: str | None = None) -> None:
    site = AjiraPortalSite()
    crawl_stats = CrawlRunStats()
    listings = await site.crawl_with_details(max_concurrency=4, stats=crawl_stats)
    discovered = len(listings)

    counts = {
        "discovered": discovered,
        "refreshed": discovered,
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "touched": 0,
    }
    await init_db()
    try:
        async with SessionLocal() as session:
            for item in listings:
                payload = _build_job_posting_payload(item)
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

        if export_path:
            export_jsonl(export_path, listings)
        else:
            payload = [item.model_dump(mode="json") for item in listings]
            print(json.dumps(payload, indent=2))
        print_end_of_run_report(
            mode="full",
            counts=counts,
            crawl_stats=crawl_stats,
            export_path=export_path,
        )
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl Ajira vacancies")
    parser.add_argument("--once", action="store_true", help="Run one crawl iteration and print JSON")
    parser.add_argument(
        "--export",
        help="Write crawled jobs to a JSONL file",
    )
    return parser.parse_args()


async def main() -> None:
    setup_logging()
    args = parse_args()
    if args.once:
        await run_once(export_path=args.export)
        return
    logger.error("No mode selected. Use --once.")


if __name__ == "__main__":
    asyncio.run(main())
