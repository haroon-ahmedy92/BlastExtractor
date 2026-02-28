"""Legacy detail model used by earlier parsing code.

The generic adapter flow now uses the typed ``JobRecord``, ``NewsRecord``, and
``ExamRecord`` models, but this structure remains useful for compatibility and
tests around older parsing helpers.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, HttpUrl


class ListingDetail(BaseModel):
    """Detailed listing payload with extracted text, attachments, and hash."""

    title: str
    institution: str | None = None
    number_of_posts: int | None = None
    deadline_date: date | None = None
    details_url: HttpUrl
    description_text: str | None = None
    description_html: str | None = None
    attachments: list[str] | None = None
    extra_metadata: dict[str, str] | None = None
    structured_fields: dict[str, str] | None = None
    content_hash: str
