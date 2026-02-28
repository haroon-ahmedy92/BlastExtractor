"""Typed job stub and record models used by job adapters.

During the crawl flow, ``JobStub`` is returned by ``discover`` and
``JobRecord`` is returned by ``fetch_details`` before being upserted into the
``job_postings`` table.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import field_validator

from app.models.common import BaseRecord, BaseStub, normalize_whitespace, parse_optional_date


class JobStub(BaseStub):
    """Lightweight job listing discovered from an index page."""

    institution: str | None = None
    number_of_posts: int | None = None
    deadline_date: date | None = None

    @property
    def details_url(self) -> str:
        """Return the detail URL as a string.

        Returns:
            str: Detail page URL.
        """

        return str(self.url)

    @field_validator("institution")
    @classmethod
    def _normalize_institution(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None

    @field_validator("deadline_date", mode="before")
    @classmethod
    def _parse_deadline(cls, value: object) -> date | None:
        return parse_optional_date(value if isinstance(value, (date, str)) else None)


class JobRecord(BaseRecord):
    """Normalized job detail record ready for database upsert."""

    title: str
    institution: str
    number_of_posts: int | None = None
    deadline_date: date | None = None
    category: str | None = None
    location: str | None = None
    description_text: str | None = None
    description_html: str | None = None
    attachments_json: dict[str, Any] | list[Any] | None = None

    @field_validator(
        "institution",
        "category",
        "location",
        "description_text",
        "description_html",
    )
    @classmethod
    def _normalize_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None

    @field_validator("deadline_date", mode="before")
    @classmethod
    def _parse_deadline(cls, value: object) -> date | None:
        return parse_optional_date(value if isinstance(value, (date, str)) else None)
