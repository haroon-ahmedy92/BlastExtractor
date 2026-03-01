"""SQLAlchemy model for stored exam results.

Exam adapters persist one normalized exam result per row in this table during
the final upsert step of the crawl flow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExamResult(Base):
    """Persistent exam result row."""

    __tablename__ = "exam_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    centre_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    centre_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    results_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
