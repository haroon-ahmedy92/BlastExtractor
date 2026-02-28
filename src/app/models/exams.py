"""Typed exam stub and record models used by exam adapters.

Exam adapters return ``ExamStub`` values from discovery and ``ExamRecord``
values from detail extraction before persistence.
"""

from __future__ import annotations

from typing import Any

from pydantic import field_validator

from app.models.common import BaseRecord, BaseStub, normalize_whitespace


class ExamStub(BaseStub):
    """Lightweight exam result reference discovered from a listing page."""

    year: int | None = None
    exam_type: str | None = None

    @field_validator("exam_type")
    @classmethod
    def _normalize_exam_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None


class ExamRecord(BaseRecord):
    """Normalized exam result ready for database upsert."""

    candidate_no: str | None = None
    year: int | None = None
    exam_type: str | None = None
    school: str | None = None
    results_json: dict[str, Any] | list[Any] | None = None

    @field_validator("candidate_no", "exam_type", "school")
    @classmethod
    def _normalize_text_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_whitespace(value)
        return normalized or None
