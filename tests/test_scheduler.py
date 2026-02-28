from __future__ import annotations

from pathlib import Path

import pytest

from app.scheduler.run import SchedulerLockError, scheduler_lock


def test_scheduler_lock_prevents_overlap(tmp_path: Path) -> None:
    lock_path = tmp_path / "scheduler.lock"

    with scheduler_lock(str(lock_path)):
        with pytest.raises(SchedulerLockError):
            with scheduler_lock(str(lock_path)):
                pass
