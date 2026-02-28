"""Placeholder exam adapter used to prove the plugin system works.

This adapter intentionally discovers nothing and performs no real scraping. It
exists so the generic crawl runner can demonstrate an exam-type adapter
without depending on a live website.
"""

from __future__ import annotations

from app.db.exam_results import upsert_exam_result
from app.models.common import ContentType, UpsertResult
from app.models.exams import ExamRecord, ExamStub
from app.sites.base import SiteAdapter
from app.sites.registry import register_adapter


class GenericExamStubAdapter(SiteAdapter[ExamStub, ExamRecord]):
    """No-op exam adapter for plugin architecture smoke tests."""

    site_name = "exam_stub"
    content_type = ContentType.EXAMS
    requires_browser = False

    async def discover(self) -> list[ExamStub]:
        """Return no discovered exam items.

        Returns:
            list[ExamStub]: Always an empty list.
        """

        self.logger.info("No-op exam adapter discover", extra={"site_name": self.site_name})
        return []

    async def fetch_details(self, stub: ExamStub) -> ExamRecord:
        """Raise because this placeholder adapter has no detail fetch step.

        Args:
            stub: Discovered stub that should never exist here.

        Returns:
            ExamRecord: Never returns.
        """

        raise RuntimeError(f"{self.site_name} has no detail fetch implementation for {stub.url}")

    async def upsert(self, record: ExamRecord) -> UpsertResult:
        """Persist an exam record if one is supplied.

        Args:
            record: Normalized exam record.

        Returns:
            UpsertResult: Summary of the database action taken.
        """

        async with self.session_factory() as db_session:
            _, upsert_result = await upsert_exam_result(db_session, record)
            await db_session.commit()
            return upsert_result


register_adapter("exam_stub", GenericExamStubAdapter)
