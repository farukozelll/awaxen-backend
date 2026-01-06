import asyncio
import os

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://awaxen:awaxen@db:5432/awaxen")


async def wait_for_db() -> None:
    conn = None
    attempt = 0
    while conn is None:
        attempt += 1
        try:
            conn = await asyncpg.connect(DATABASE_URL.replace("+asyncpg", ""))
        except Exception:  # noqa: BLE001
            await asyncio.sleep(1)
        else:
            await conn.close()
            break


if __name__ == "__main__":
    asyncio.run(wait_for_db())
