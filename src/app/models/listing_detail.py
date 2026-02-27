from __future__ import annotations

from datetime import date

from pydantic import BaseModel, HttpUrl


class ListingDetail(BaseModel):
    title: str
    institution: str | None = None
    number_of_posts: int | None = None
    deadline_date: date | None = None
    details_url: HttpUrl
    description_text: str | None = None
    description_html: str | None = None
    attachments: list[str] | None = None
    extra_metadata: dict[str, str] | None = None
    content_hash: str
