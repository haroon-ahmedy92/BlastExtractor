"""Typed news stub and record models used by news adapters.

``NewsStub`` represents a discovered article link and ``NewsRecord`` is the
normalized detail payload that gets upserted into ``news_articles``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import field_validator

from app.models.common import BaseRecord, BaseStub, normalize_whitespace


class NewsStub(BaseStub):
    """Lightweight news article discovered from a listing page."""

    published_at: datetime | None = None

    @field_validator("published_at", mode="before")
    @classmethod
    def _parse_published_at(cls, value: object) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text = normalize_whitespace(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        raise ValueError(f"Unsupported published_at value: {value}")


class NewsRecord(BaseRecord):
    """Normalized news article ready for database upsert."""

    title: str
    author: str | None = None
    published_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    tags_json: dict[str, Any] | list[Any] | None = None
    attachments_json: dict[str, Any] | list[Any] | None = None

    @field_validator("author", "body_text", "body_html")
    @classmethod
    def _normalize_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None
