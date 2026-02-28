"""Persistence helpers for exam result records.

Exam adapters call :func:`upsert_exam_result` after ``fetch_details`` returns a
typed exam record. The function updates timestamps and only rewrites fields
when the record hash changes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.common import UpsertAction, UpsertResult
from app.models.exam_result import ExamResult
from app.models.exams import ExamRecord


async def upsert_exam_result(
    session: AsyncSession,
    record: ExamRecord,
) -> tuple[ExamResult, UpsertResult]:
    """Insert or update an exam result row.

    Args:
        session: Active database session.
        record: Normalized exam record from an adapter.

    Returns:
        tuple[ExamResult, UpsertResult]: Stored ORM row and action summary.
    """

    query_result = await session.execute(
        select(ExamResult).where(ExamResult.source_url == str(record.source_url))
    )
    existing_exam_result = query_result.scalar_one_or_none()
    current_time = datetime.now(UTC)

    if existing_exam_result is not None:
        existing_exam_result.last_seen = current_time
        existing_exam_result.source = record.source
        action: UpsertAction = "unchanged"
        if existing_exam_result.content_hash != record.content_hash:
            existing_exam_result.title = record.title
            existing_exam_result.candidate_no = record.candidate_no
            existing_exam_result.year = record.year
            existing_exam_result.exam_type = record.exam_type
            existing_exam_result.school = record.school
            existing_exam_result.results_json = record.results_json
            existing_exam_result.content_hash = record.content_hash
            action = "updated"
        await session.flush()
        return existing_exam_result, UpsertResult(
            action=action,
            record_id=existing_exam_result.id,
        )

    new_exam_result = ExamResult(
        source=record.source,
        source_url=str(record.source_url),
        title=record.title,
        candidate_no=record.candidate_no,
        year=record.year,
        exam_type=record.exam_type,
        school=record.school,
        results_json=record.results_json,
        content_hash=record.content_hash,
        first_seen=current_time,
        last_seen=current_time,
    )
    session.add(new_exam_result)
    await session.flush()
    return new_exam_result, UpsertResult(action="inserted", record_id=new_exam_result.id)
