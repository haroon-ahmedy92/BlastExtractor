"""Typed news stub and record models used by news adapters.

``NewsStub`` represents a discovered article link and ``NewsRecord`` is the
normalized detail payload that gets upserted into ``news_articles``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import field_validator

from app.models.common import BaseRecord, BaseStub, normalize_whitespace, parse_optional_datetime


class NewsStub(BaseStub):
    """Lightweight news article discovered from a listing page."""

    published_at: datetime | None = None

    @field_validator("published_at", mode="before")
    @classmethod
    def _parse_published_at(cls, value: object) -> datetime | None:
        if value is None or value == "":
            return None
        parsed = parse_optional_datetime(value if isinstance(value, (datetime, str)) else None)
        if parsed is None:
            raise ValueError(f"Unsupported published_at value: {value}")
        return parsed


class NewsRecord(BaseRecord):
    """Normalized news article ready for database upsert."""

    title: str
    author: str | None = None
    published_at: datetime | None = None
    section: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    tags_json: dict[str, Any] | list[Any] | None = None
    attachments_json: dict[str, Any] | list[Any] | None = None

    @field_validator("author", "section", "body_text", "body_html")
    @classmethod
    def _normalize_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None
