"""Small legacy job listing model.

This model predates the richer adapter-based job record types and remains as a
simple typed container for basic job links.
"""

from pydantic import BaseModel, HttpUrl


class JobListing(BaseModel):
    """Minimal job listing with title, URL, and source."""

    title: str
    url: HttpUrl
    source: str
