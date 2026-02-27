from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.crawler.crawl_ajira import should_refresh_listing_detail
from app.models.job_posting import JobPosting
from app.models.listing_stub import ListingStub
from app.scheduler.run import SchedulerLockError, scheduler_lock


def _build_stub() -> ListingStub:
    return ListingStub(
        title="Data Engineer",
        institution="Public Data Agency",
        number_of_posts=2,
        deadline_date=date(2026, 3, 10),
        details_url="https://example.com/jobs/1",
    )


def _build_posting(*, last_seen: datetime, title: str = "Data Engineer") -> JobPosting:
    return JobPosting(
        id=1,
        source="ajira_portal",
        source_url="https://example.com/jobs/1",
        title=title,
        institution="Public Data Agency",
        number_of_posts=2,
        deadline_date=date(2026, 3, 10),
        category="Engineering",
        location="Dodoma",
        description_text="Build reliable data pipelines",
        description_html="<p>Build reliable data pipelines</p>",
        attachments_json=None,
        content_hash="hash-1",
        first_seen=last_seen,
        last_seen=last_seen,
    )


def test_should_refresh_listing_detail_for_new_job() -> None:
    stub = _build_stub()
    now = datetime.now(UTC)

    assert should_refresh_listing_detail(
        stub,
        None,
        refresh_after_days=7,
        now=now,
    ) is True


def test_should_refresh_listing_detail_for_changed_metadata() -> None:
    stub = _build_stub()
    now = datetime.now(UTC)
    posting = _build_posting(last_seen=now, title="Senior Data Engineer")

    assert should_refresh_listing_detail(
        stub,
        posting,
        refresh_after_days=7,
        now=now,
    ) is True


def test_should_refresh_listing_detail_for_stale_job() -> None:
    stub = _build_stub()
    now = datetime.now(UTC)
    posting = _build_posting(last_seen=now - timedelta(days=8))

    assert should_refresh_listing_detail(
        stub,
        posting,
        refresh_after_days=7,
        now=now,
    ) is True


def test_should_not_refresh_listing_detail_for_fresh_unchanged_job() -> None:
    stub = _build_stub()
    now = datetime.now(UTC)
    posting = _build_posting(last_seen=now - timedelta(days=2))

    assert should_refresh_listing_detail(
        stub,
        posting,
        refresh_after_days=7,
        now=now,
    ) is False


def test_scheduler_lock_prevents_overlap(tmp_path: Path) -> None:
    lock_path = tmp_path / "scheduler.lock"

    with scheduler_lock(str(lock_path)):
        with pytest.raises(SchedulerLockError):
            with scheduler_lock(str(lock_path)):
                pass
