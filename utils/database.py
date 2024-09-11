import pathlib
import sqlite3
from warnings import warn
import aiosqlite
import asyncio
import typing as t
import time
from colorama import Fore, Style


reset = Style.RESET_ALL


class Connection(aiosqlite.Connection):
    def __init__(self, *args, **kwargs) -> None:
        self.lock = asyncio.Lock()
        super().__init__(*args, **kwargs)

    async def _connect(self) -> t.Self:
        db = await super()._connect()
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA wal_autocheckpoint = 2048;")
        return self

    async def close(self) -> None:
        await super().close()


class ConnectionPool:
    def __init__(
        self, db_path: str, min_pool_size: int = 2,
        max_pool_size: int = 15, idle_timeout: int = 600
    ):
        self.db_path = db_path
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.idle_timeout = idle_timeout
        self.pool: asyncio.Queue[Connection] = asyncio.Queue()
        self.connection_timestamps: dict[Connection, float] = {}
        self.current_size = 0
        self.lock = asyncio.Lock()

    async def init_pool(self):
        for _ in range(self.min_pool_size):
            conn = await self._create_new_connection()
            await self.pool.put(conn)
            self.connection_timestamps[conn] = time.time()
        asyncio.create_task(self.cleanup())

    async def _create_new_connection(self) -> Connection:
        conn = await connect(self.db_path)
        self.current_size += 1
        self._connect_log()
        return conn  # type: ignore

    def _calculate_timeout(self) -> float:
        base_timeout = 1
        return base_timeout + (self.current_size / 2)

    def _connect_log(self):
        color = f"{Fore.GREEN}{Style.BRIGHT}"
        print(f"{color}Connected {self.db_path} ({self.current_size}) {reset}")

    def _disconnect_log(self):
        color = f"{Fore.RED}{Style.BRIGHT}"
        print(
            f"{color}Disconnected {self.db_path} ({self.current_size}) {reset}"
        )

    async def acquire(self) -> Connection:
        timeout = self._calculate_timeout()
        try:
            conn = await asyncio.wait_for(self.pool.get(), timeout=timeout)
            if (
                time.time() - self.connection_timestamps.get(conn, 0)
                > self.idle_timeout
            ):
                await conn.close()
                self._disconnect_log()
                self.connection_timestamps.pop(conn, None)
                conn = await self._create_new_connection()
            return conn
        except asyncio.TimeoutError:
            async with self.lock:
                if self.current_size < self.max_pool_size:
                    return await self._create_new_connection()
                else:
                    return await self.pool.get()

    async def release(self, connection: Connection):
        self.connection_timestamps[connection] = time.time()
        await self.pool.put(connection)

    async def close_all(self):
        while not self.pool.empty():
            conn = await self.pool.get()
            await conn.close()
            self._disconnect_log()
            self.current_size -= 1
        self.current_size = 0
        self.connection_timestamps.clear()

    async def cleanup(self):
        while True:
            await asyncio.sleep(self.idle_timeout)
            to_close = []
            async with self.lock:
                while (
                    self.current_size > self.min_pool_size
                    and not self.pool.empty()
                ):
                    conn = await self.pool.get()
                    if (
                        time.time() - self.connection_timestamps.get(conn, 0)
                        > self.idle_timeout
                    ):
                        to_close.append(conn)
                    else:
                        await self.pool.put(conn)
            for conn in to_close:
                await conn.close()
                self.current_size -= 1
                self._disconnect_log()
                self.connection_timestamps.pop(conn, None)

    def __await__(self):
        return self.init_pool().__await__()


class Transaction:
    def __init__(
        self, connection: aiosqlite.Connection | Connection | ConnectionPool,
        manual_commit: bool = False
    ) -> None:
        if not isinstance(connection, (Connection, ConnectionPool)):
            warn(
                "use database.Connection instead of aiosqlite.Connection" +
                "for the transaction to work correctly"
            )

        self.connection = connection
        self.manual_commit = manual_commit
        self._transaction_started = False

        self._conn = None

    async def __aenter__(self):
        if isinstance(self.connection, Connection):
            await self.connection.lock.acquire()
            self._conn = self.connection
        elif isinstance(self.connection, ConnectionPool):
            self._conn = await self.connection.acquire()
        else:
            self._conn = self.connection

        if not self._transaction_started:
            await self._conn.execute("BEGIN;")
            self._transaction_started = True

        return self._conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._transaction_started:
            if exc_type is None:
                if not self.manual_commit:
                    await self._conn.commit()
            else:
                await self._conn.rollback()
        self._transaction_started = False

        if isinstance(self.connection, Connection):
            self.connection.lock.release()
        elif isinstance(self.connection, ConnectionPool):
            await self.connection.release(self._conn)


async def initialize_database(db: aiosqlite.Connection):
    async with Transaction(db):
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                avatar_url TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_keys (
                user_id INTEGER NOT NULL,
                token_secret TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
                ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_user_id ON auth_keys(user_id);
            """
        )


def connect(
    database: str | pathlib.Path,
    *,
    iter_chunk_size=64,
    **kwargs: t.Any,
) -> Connection:

    def connector() -> sqlite3.Connection:
        if isinstance(database, str):
            loc = database
        elif isinstance(database, bytes):
            loc = database.decode("utf-8")
        else:
            loc = str(database)

        return sqlite3.connect(loc, **kwargs)

    return Connection(connector, iter_chunk_size)
