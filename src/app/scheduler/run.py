from __future__ import annotations

import argparse
import asyncio
import fcntl
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import get_settings
from app.crawler.crawl_ajira import sync_ajira_incremental
from app.logging import setup_logging

logger = logging.getLogger(__name__)


class SchedulerLockError(RuntimeError):
    pass


@contextmanager
def scheduler_lock(lock_path: str) -> Iterator[None]:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SchedulerLockError(f"Scheduler already running: {lock_path}") from exc
        handle.write(str(Path.cwd()))
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


async def run_cycle() -> dict[str, int]:
    settings = get_settings()
    counts, _ = await sync_ajira_incremental(
        max_concurrency=4,
        refresh_after_days=settings.scheduler_refresh_after_days,
    )
    return counts


async def run_forever() -> None:
    settings = get_settings()
    interval_seconds = max(60, settings.scheduler_interval_minutes * 60)
    while True:
        try:
            await run_cycle()
        except Exception:
            logger.exception("Scheduled Ajira crawl failed")
        logger.info(
            "Scheduler sleeping",
            extra={"interval_minutes": settings.scheduler_interval_minutes},
        )
        await asyncio.sleep(interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the BlastExtractor scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single incremental crawl cycle and exit",
    )
    return parser.parse_args()


async def main() -> None:
    setup_logging()
    settings = get_settings()
    args = parse_args()

    with scheduler_lock(settings.scheduler_lock_path):
        if args.once:
            await run_cycle()
            return
        await run_forever()


if __name__ == "__main__":
    asyncio.run(main())
