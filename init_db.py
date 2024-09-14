from utils.database import initialize_database
import asyncio
import json
import asyncpg


async def main():
    print(":: Running PostgreSQL init scripts")
    with open("postgres.json") as f:
        config = json.load(f)
    conn = await asyncpg.connect(**config)
    await initialize_database(conn)
    await conn.close()
    print(":: Done!")


if __name__ == "__main__":
    asyncio.run(main())
