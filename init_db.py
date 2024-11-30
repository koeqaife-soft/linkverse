from utils.database import initialize_database
from core import setup_logger
import asyncio
import json
import asyncpg

logger = setup_logger()


async def main():
    logger.info("Running PostgreSQL init scripts")
    with open("config/postgres.json") as f:
        config = json.load(f)
        config.pop("max_shared", None)
    conn = await asyncpg.connect(**config)
    await initialize_database(conn, debug=True)
    await conn.close()
    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
