import os
import re
import asyncpg
from core import worker_count, _logger
from _types import connection_type


def calculate_max_connections(max_shared: int, worker_count: int) -> int:
    _worker_count = max(worker_count, 1)
    _max_shared = max(max_shared - 5, 1)

    max_connections = _max_shared // _worker_count

    return max(max_connections, 1)


async def create_pool(**config) -> asyncpg.pool.Pool:
    max_shared = int(config.pop("max_shared", 100))
    max_connections = calculate_max_connections(max_shared, worker_count)

    pool = await asyncpg.create_pool(
        **config,
        min_size=1,
        max_size=max_connections
    )
    if pool is None:
        raise
    return pool


async def execute_sql_file(db: connection_type, file_path: str):
    with open(file_path, 'r') as file:
        sql = file.read()
        await db.execute(sql)


async def initialize_database(
    db: connection_type, sql_dir: str = "./sql/",
    debug: bool = False
) -> None:
    sql_files = [f for f in os.listdir(sql_dir) if f.endswith('.pgsql')]

    def extract_number(filename: str) -> int:
        match = re.match(r'(\d+)', filename)
        return int(match.group()) if match else int('inf')

    sql_files.sort(key=extract_number)

    async with db.transaction():
        for sql_file in sql_files:
            file_path = os.path.join(sql_dir, sql_file)
            ((_logger.info if debug else _logger.debug)
             (f"Running {file_path}..."))
            await execute_sql_file(db, file_path)
