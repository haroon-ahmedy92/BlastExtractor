"""Scheduler entry point for recurring crawl runs.

This module repeatedly calls the generic crawler runner on a fixed interval.
In the overall crawl flow it sits above the runner and ensures that only one
scheduler process is active at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import get_settings
from app.crawler.run import print_report, run_site_once
from app.logging import setup_logging

logger = logging.getLogger(__name__)


class SchedulerLockError(RuntimeError):
    """Raised when another scheduler process already holds the lock."""

    pass


@contextmanager
def scheduler_lock(lock_path: str) -> Iterator[None]:
    """Acquire a non-blocking filesystem lock for the scheduler.

    Args:
        lock_path: File path used for the lock.

    Yields:
        Iterator[None]: Control while the lock is held.

    Raises:
        SchedulerLockError: If another scheduler process already holds the lock.
    """

    lock_file_path = Path(lock_path)
    lock_file_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_file_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SchedulerLockError(f"Scheduler already running: {lock_path}") from error
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


async def run_cycle() -> None:
    """Run one scheduled crawl cycle for Ajira.

    Returns:
        None
    """

    report = await run_site_once(site_name="ajira", concurrency=4)
    print_report(report)


async def run_forever() -> None:
    """Run scheduled crawl cycles forever.

    Returns:
        None
    """

    settings = get_settings()
    interval_seconds = max(60, settings.scheduler_interval_minutes * 60)
    while True:
        try:
            await run_cycle()
        except Exception:
            logger.exception("Scheduled crawl failed")
        await asyncio.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    """Parse scheduler command-line arguments.

    Returns:
        argparse.Namespace: Parsed CLI arguments.
    """

    parser = argparse.ArgumentParser(description="Run the BlastExtractor scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    return parser.parse_args()


async def main() -> None:
    """Run the scheduler CLI.

    Returns:
        None
    """

    setup_logging()
    settings = get_settings()
    cli_args = parse_args()
    with scheduler_lock(settings.scheduler_lock_path):
        if cli_args.once:
            await run_cycle()
            return
        await run_forever()


if __name__ == "__main__":
    asyncio.run(main())
