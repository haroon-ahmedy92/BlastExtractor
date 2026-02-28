"""Shared Pydantic and SQLAlchemy models for crawl data.

This package defines the typed stubs and records used in the crawl flow, plus
the database tables that adapters upsert into after fetching details.
"""

from app.models.common import BaseRecord, BaseStub, ContentType, UpsertResult
from app.models.exam_result import ExamResult
from app.models.exams import ExamRecord, ExamStub
from app.models.job_posting import JobPosting
from app.models.jobs import JobRecord, JobStub
from app.models.news import NewsRecord, NewsStub
from app.models.news_article import NewsArticle

__all__ = [
    "BaseRecord",
    "BaseStub",
    "ContentType",
    "UpsertResult",
    "JobPosting",
    "NewsArticle",
    "ExamResult",
    "JobStub",
    "JobRecord",
    "NewsStub",
    "NewsRecord",
    "ExamStub",
    "ExamRecord",
]
