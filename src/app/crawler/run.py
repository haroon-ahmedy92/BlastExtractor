"""Generic CLI runner for site adapters.

This module is the center of the crawl flow. It parses CLI arguments, loads an
adapter from the registry, opens the shared browser context when needed,
processes stubs concurrently, performs upserts, and prints the final summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from app.crawler.browser import browser_context
from app.db.session import SessionLocal, engine, init_db
from app.logging import setup_logging
from app.models.common import BaseRecord, UpsertResult
from app.sites.registry import get_adapter


@dataclass(slots=True)
class CrawlReport:
    """Summary counts collected during one crawl run."""

    site: str
    discovered: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    duration_seconds: float = 0.0


def export_jsonl(path: str, records: Sequence[BaseRecord]) -> None:
    """Write fetched records to a JSON Lines file.

    Args:
        path: Target file path.
        records: Records fetched during the crawl run.

    Returns:
        None
    """

    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False))
            output_file.write("\n")


async def run_site_once(
    *,
    site_name: str,
    concurrency: int,
    export_jsonl_path: str | None = None,
) -> CrawlReport:
    """Run one site adapter from discovery through upsert.

    Args:
        site_name: Registry name for the adapter.
        concurrency: Maximum concurrent detail fetches.
        export_jsonl_path: Optional JSONL export destination.

    Returns:
        CrawlReport: Final crawl summary.
    """

    started_at = perf_counter()
    report = CrawlReport(site=site_name)
    records: list[BaseRecord] = []
    await init_db()
    try:
        adapter_cls = get_adapter(site_name)
        if adapter_cls.requires_browser:
            async with browser_context() as shared_browser_context:
                adapter = adapter_cls(
                    browser_context=shared_browser_context,
                    session_factory=SessionLocal,
                )
                report, records = await _run_adapter(adapter, concurrency, report)
        else:
            adapter = adapter_cls(browser_context=None, session_factory=SessionLocal)
            report, records = await _run_adapter(adapter, concurrency, report)

        if export_jsonl_path:
            export_jsonl(export_jsonl_path, records)
    finally:
        await engine.dispose()

    report.duration_seconds = round(perf_counter() - started_at, 2)
    return report


async def _run_adapter(
    adapter,
    concurrency: int,
    report: CrawlReport,
) -> tuple[CrawlReport, list[BaseRecord]]:
    """Process discovered stubs and persist fetched records.

    Args:
        adapter: Site adapter instance.
        concurrency: Maximum concurrent detail fetches.
        report: Mutable report object for counters.

    Returns:
        tuple[CrawlReport, list[BaseRecord]]: Updated report and fetched records.
    """

    records: list[BaseRecord] = []
    discovered_stubs = await adapter.discover()
    report.discovered = len(discovered_stubs)
    semaphore = asyncio.Semaphore(max(1, min(8, concurrency)))

    async def process_stub(stub) -> UpsertResult | None:
        async with semaphore:
            try:
                record = await adapter.fetch_details(stub)
                records.append(record)
                return await adapter.upsert(record)
            except Exception:
                report.failed += 1
                adapter.logger.exception(
                    "Failed to process stub",
                    extra={"site_name": adapter.site_name, "url": str(stub.url)},
                )
                return None

    upsert_results = await asyncio.gather(*(process_stub(stub) for stub in discovered_stubs))
    for upsert_result in upsert_results:
        if upsert_result is None:
            continue
        if upsert_result.action == "inserted":
            report.inserted += 1
        elif upsert_result.action == "updated":
            report.updated += 1
        else:
            report.unchanged += 1
    return report, records


def print_report(report: CrawlReport, export_jsonl_path: str | None = None) -> None:
    """Print the final crawl summary to standard error.

    Args:
        report: Final crawl summary.
        export_jsonl_path: Optional JSONL export destination.

    Returns:
        None
    """

    lines = [
        "",
        "Crawler Report",
        f"site: {report.site}",
        f"discovered: {report.discovered}",
        f"inserted: {report.inserted}",
        f"updated: {report.updated}",
        f"unchanged: {report.unchanged}",
        f"failed: {report.failed}",
        f"duration_seconds: {report.duration_seconds}",
    ]
    if export_jsonl_path:
        lines.append(f"export_jsonl: {export_jsonl_path}")
    print("\n".join(lines), file=sys.stderr)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the generic crawler runner.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """

    parser = argparse.ArgumentParser(description="Run a crawler site adapter")
    parser.add_argument("--site", required=True, help="Adapter site name from the registry")
    parser.add_argument("--once", action="store_true", help="Run one crawl cycle and exit")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent detail fetches")
    parser.add_argument("--export-jsonl", help="Optional JSONL export path")
    return parser.parse_args()


async def main() -> None:
    """Run the generic crawler CLI.

    Returns:
        None
    """

    setup_logging()
    cli_args = parse_args()
    if not cli_args.once:
        raise SystemExit("Only --once is supported by this runner")
    report = await run_site_once(
        site_name=cli_args.site,
        concurrency=cli_args.concurrency,
        export_jsonl_path=cli_args.export_jsonl,
    )
    print_report(report, export_jsonl_path=cli_args.export_jsonl)


if __name__ == "__main__":
    asyncio.run(main())
