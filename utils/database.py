import os
import re
import asyncpg
from core import worker_count, _logger
import typing as t
from collections import defaultdict


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


async def execute_sql_file(db: asyncpg.Connection, file_path: str):
    with open(file_path, 'r') as file:
        sql = file.read()
        await db.execute(sql)


async def initialize_database(
    db: asyncpg.Connection, sql_dir: str = "./sql/",
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


def condition(
    value: t.Any | None, parameter: int
) -> t.Tuple[str, t.List[t.Any]]:
    if value is None:
        return "IS NULL", []
    return f"= ${parameter}", [value]


class AutoConnection:
    # TODO: Transactions
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.temp_cache: defaultdict[str, t.Any] = defaultdict(lambda: None)
        self._conn = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self._conn is not None:
            await self.pool.release(self._conn)

    async def create_conn(self, **kwargs):
        if self._conn is not None and not self._conn.is_closed():
            return self._conn
        self._conn = await self.pool.acquire(**kwargs)
        return self._conn
