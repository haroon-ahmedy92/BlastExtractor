"""Abstract base class for site adapters.

This module defines the contract that all site plugins must follow. The
generic crawler runner depends on this interface so it can stay unaware of any
site-specific scraping details.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.common import BaseRecord, BaseStub, ContentType, UpsertResult


class SiteAdapter[StubT: BaseStub, RecordT: BaseRecord](ABC):
    """Base class for site-specific crawl plugins."""

    site_name: str
    content_type: ContentType
    requires_browser: bool = True

    def __init__(
        self,
        *,
        browser_context: Any | None,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Store shared runtime dependencies for an adapter.

        Args:
            browser_context: Shared Playwright browser context or ``None``.
            session_factory: Async SQLAlchemy session factory.
        """

        self.browser_context = browser_context
        self.session_factory = session_factory
        self.logger = logging.LoggerAdapter(
            logging.getLogger(self.site_name),
            {
                "site_name": self.site_name,
                "content_type": self.content_type.value,
            },
        )

    @abstractmethod
    async def discover(self) -> list[StubT]:
        """Discover listing stubs for this site.

        Returns:
            list[StubT]: Lightweight stubs to process.
        """

        raise NotImplementedError

    @abstractmethod
    async def fetch_details(self, stub: StubT) -> RecordT:
        """Fetch and normalize a full record for one discovered stub.

        Args:
            stub: Lightweight discovered item.

        Returns:
            RecordT: Normalized detail record.
        """

        raise NotImplementedError

    @abstractmethod
    async def upsert(self, record: RecordT) -> UpsertResult:
        """Persist one normalized record into the adapter's table.

        Args:
            record: Normalized detail record.

        Returns:
            UpsertResult: Summary of the database action taken.
        """

        raise NotImplementedError
