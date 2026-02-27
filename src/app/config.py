import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_env: str
    app_name: str
    log_level: str
    database_url: str
    ajira_url: str
    crawler_timeout_seconds: int
    scheduler_interval_minutes: int
    scheduler_refresh_after_days: int
    scheduler_lock_path: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
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
        scheduler_interval_minutes=int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "30")),
        scheduler_refresh_after_days=int(os.getenv("SCHEDULER_REFRESH_AFTER_DAYS", "7")),
        scheduler_lock_path=os.getenv("SCHEDULER_LOCK_PATH", "/tmp/blastextractor-scheduler.lock"),
    )
