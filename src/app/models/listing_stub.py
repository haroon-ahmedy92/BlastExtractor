"""Legacy listing stub model used by older parser helpers.

This model is simpler than the newer adapter-specific stub models, but it
still represents the same idea: a lightweight item discovered from a listing
page before full detail fetching.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, HttpUrl


class ListingStub(BaseModel):
    """Minimal listing stub with metadata from a list page."""

    title: str
    institution: str | None = None
    number_of_posts: int | None = None
    deadline_date: date | None = None
    details_url: HttpUrl
