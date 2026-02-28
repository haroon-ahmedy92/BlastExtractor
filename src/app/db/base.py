"""Shared SQLAlchemy declarative base.

All table models inherit from :class:`Base`. The database initialization step
imports model modules so their tables are attached to this metadata object
before ``create_all`` runs.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass
