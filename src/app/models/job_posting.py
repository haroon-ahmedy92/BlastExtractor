"""SQLAlchemy model for stored job postings.

Job adapters upsert into this table after fetching and normalizing detail
pages. The API reads from this table when serving job endpoints.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JobPosting(Base):
    """Persistent job posting row."""

    __tablename__ = "job_postings"

    long_text_type = Text().with_variant(mysql.LONGTEXT(), "mysql")  # type: ignore[no-untyped-call]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    institution: Mapped[str] = mapped_column(String(255), nullable=False)

    number_of_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    category: Mapped[str | None] = mapped_column(long_text_type, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_text: Mapped[str | None] = mapped_column(long_text_type, nullable=True)
    description_html: Mapped[str | None] = mapped_column(long_text_type, nullable=True)
    attachments_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
