"""Shared enums, base models, and normalization helpers.

This module defines the common building blocks used by all adapters:
``BaseStub`` for discovery results, ``BaseRecord`` for normalized detail
records, and small helpers that make hashing and validation more stable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


def normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace into single spaces.

    Args:
        value: Input text.

    Returns:
        str: Normalized text.
    """

    return " ".join(value.split())


def parse_optional_date(value: date | datetime | str | None) -> date | None:
    """Parse a date value in a small set of supported formats.

    Args:
        value: Date-like value or ``None``.

    Returns:
        date | None: Parsed date or ``None`` when input is empty.

    Raises:
        ValueError: If the date string does not match the supported formats.
    """

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize_whitespace(value)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


class ContentType(str, Enum):
    """Known content groups handled by the crawler."""

    JOBS = "jobs"
    NEWS = "news"
    EXAMS = "exams"


UpsertAction = Literal["inserted", "updated", "unchanged"]


class UpsertResult(BaseModel):
    """Summary of the database action taken for one record."""

    action: UpsertAction
    record_id: int | None = None


class BaseStub(BaseModel):
    """Base model for lightweight discovery results."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: HttpUrl
    title: str | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None


class BaseRecord(BaseModel):
    """Base model for normalized detail records stored by adapters."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source: str
    source_url: HttpUrl
    title: str | None = None
    content_hash: str

    @field_validator("source", "title")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None
