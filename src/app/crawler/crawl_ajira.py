"""Compatibility CLI for running the Ajira adapter directly.

This module is a thin wrapper around the generic crawler runner. It keeps the
older ``crawl-ajira`` style flow available while delegating actual crawl work
to :mod:`app.crawler.run`.
"""

from __future__ import annotations

import argparse
import asyncio

from app.crawler.run import print_report, run_site_once
from app.logging import setup_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the Ajira wrapper command.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """

    parser = argparse.ArgumentParser(description="Crawl Ajira vacancies")
    parser.add_argument("--once", action="store_true", help="Run one crawl iteration and exit")
    parser.add_argument("--export", help="Optional JSONL export path")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent detail fetches")
    return parser.parse_args()


async def main() -> None:
    """Run the Ajira crawler wrapper once.

    Returns:
        None
    """

    setup_logging()
    cli_args = parse_args()
    if not cli_args.once:
        raise SystemExit("Use --once")
    report = await run_site_once(
        site_name="ajira",
        concurrency=cli_args.concurrency,
        export_jsonl_path=cli_args.export,
    )
    print_report(report, export_jsonl_path=cli_args.export)


if __name__ == "__main__":
    asyncio.run(main())
