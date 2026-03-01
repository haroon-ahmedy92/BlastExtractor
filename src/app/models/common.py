"""Shared enums, base models, and normalization helpers.

This module defines the common building blocks used by all adapters:
``BaseStub`` for discovery results, ``BaseRecord`` for normalized detail
records, and small helpers that make hashing and validation more stable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator

HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


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


def parse_optional_datetime(value: datetime | str | None) -> datetime | None:
    """Parse a datetime value in a small set of supported formats.

    Args:
        value: Datetime-like value or ``None``.

    Returns:
        datetime | None: Parsed datetime or ``None`` when input is empty.
    """

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    text = normalize_whitespace(value)
    candidates = (
        text.replace("Z", "+00:00"),
        text,
    )
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    for fmt in (
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%A, %B %d, %Y - %H:%M",
        "%A, %B %d, %Y",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def validate_http_url(url: str) -> HttpUrl:
    """Validate and normalize a raw string URL into ``HttpUrl``.

    Args:
        url: Raw URL string.

    Returns:
        HttpUrl: Validated Pydantic URL object.
    """

    return HTTP_URL_ADAPTER.validate_python(url)


def compute_content_hash(payload: Mapping[str, object]) -> str:
    """Compute a stable hash for a normalized record payload.

    Args:
        payload: JSON-serializable content payload.

    Returns:
        str: SHA-256 hex digest.
    """

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ContentType(StrEnum):
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
