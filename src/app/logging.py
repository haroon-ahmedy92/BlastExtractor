"""Structured logging setup used across the application.

This module provides a JSON formatter and a helper to configure root logging.
The crawler runner, adapters, scheduler, and API call :func:`setup_logging`
early so crawl events include useful metadata such as ``site_name``.
"""

import json
import logging
from datetime import UTC, datetime

from app.config import get_settings

RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    """Format log records as JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record as a JSON line.

        Args:
            record: Standard Python log record.

        Returns:
            str: JSON-encoded log payload.
        """

        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in RESERVED_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        payload.update(extras)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    """Configure the root logger for JSON output.

    Returns:
        None
    """

    settings = get_settings()
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
