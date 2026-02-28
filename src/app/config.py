"""Configuration loading for crawler, API, and scheduler settings.

This module reads environment variables into the :class:`Settings` dataclass.
The rest of the crawl flow depends on these values for browser timeouts,
database access, scheduler timing, and site URLs.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Immutable application settings loaded from environment variables."""

    app_env: str
    app_name: str
    log_level: str
    database_url: str
    ajira_url: str
    crawler_timeout_seconds: int
    browser_headless: bool
    browser_timeout_ms: int
    browser_rate_limit_seconds: float
    scheduler_interval_minutes: int
    scheduler_refresh_after_days: int
    scheduler_lock_path: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache application settings.

    Returns:
        Settings: Frozen configuration shared across the app.
    """

    load_dotenv()

    browser_headless = os.getenv("BROWSER_HEADLESS", "true").lower() in {"1", "true", "yes", "on"}
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        app_name=os.getenv("APP_NAME", "BlastExtractor"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_url=os.getenv(
            "DATABASE_URL",
            "mysql+aiomysql://haroon:amaniamani@127.0.0.1:3306/BlastExtractor",
        ),
        ajira_url=os.getenv("AJIRA_URL", "https://www.ajira.go.tz/"),
        crawler_timeout_seconds=int(os.getenv("CRAWLER_TIMEOUT_SECONDS", "30")),
        browser_headless=browser_headless,
        browser_timeout_ms=int(os.getenv("BROWSER_TIMEOUT_MS", "30000")),
        browser_rate_limit_seconds=float(os.getenv("BROWSER_RATE_LIMIT_SECONDS", "0.25")),
        scheduler_interval_minutes=int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "30")),
        scheduler_refresh_after_days=int(os.getenv("SCHEDULER_REFRESH_AFTER_DAYS", "7")),
        scheduler_lock_path=os.getenv("SCHEDULER_LOCK_PATH", "/tmp/blastextractor-scheduler.lock"),
    )
