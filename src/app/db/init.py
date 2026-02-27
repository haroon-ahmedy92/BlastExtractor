import asyncio

from app.db.session import engine, init_db


async def _main() -> None:
    await init_db()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
