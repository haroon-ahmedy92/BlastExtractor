from __future__ import annotations

from datetime import date

from pydantic import BaseModel, HttpUrl


class ListingStub(BaseModel):
    title: str
    institution: str | None = None
    number_of_posts: int | None = None
    deadline_date: date | None = None
    details_url: HttpUrl
