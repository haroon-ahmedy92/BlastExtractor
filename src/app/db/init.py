"""CLI helper for creating all database tables.

This module is a small entry point around :func:`app.db.session.init_db`. It
is usually run before the crawler or API starts for the first time.
"""

import asyncio

from app.db.session import engine, init_db


async def _main() -> None:
    """Create all tables and dispose the shared engine.

    Returns:
        None
    """

    await init_db()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
