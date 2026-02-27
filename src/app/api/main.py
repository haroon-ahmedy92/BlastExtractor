from fastapi import FastAPI

from app.config import get_settings
from app.db.session import init_db
from app.logging import setup_logging

setup_logging()
settings = get_settings()

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
