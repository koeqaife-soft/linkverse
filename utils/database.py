import math
import os
import re
import asyncpg
from core import worker_count


async def create_pool(**config) -> asyncpg.pool.Pool:
    _max_shared = max(int(config.get("max_shared", 100))-5, 1)
    max_connections = max(math.ceil(_max_shared/worker_count), 1)

    pool = await asyncpg.create_pool(
        **config,
        min_size=1,
        max_size=max_connections
    )
    if pool is None:
        raise
    return pool


async def execute_sql_file(db: asyncpg.Connection, file_path: str):
    with open(file_path, 'r') as file:
        sql = file.read()
        await db.execute(sql)


async def initialize_database(db: asyncpg.Connection, sql_dir: str = "./sql/"):
    sql_files = [f for f in os.listdir(sql_dir) if f.endswith('.pgsql')]

    def extract_number(filename: str) -> int:
        match = re.match(r'(\d+)', filename)
        return int(match.group()) if match else int('inf')

    sql_files.sort(key=extract_number)

    async with db.transaction():
        for sql_file in sql_files:
            file_path = os.path.join(sql_dir, sql_file)
            await execute_sql_file(db, file_path)
