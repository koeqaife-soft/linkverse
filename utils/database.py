import pathlib
import sqlite3
from warnings import warn
import aiosqlite
import asyncio
import typing as t


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


class Transaction:
    def __init__(
        self, connection: aiosqlite.Connection | Connection,
        manual_commit: bool = False
    ) -> None:
        if not isinstance(connection, Connection):
            warn(
                "Use database.Connection instead of aiosqlite.Connection "
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
        self._conn = None


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
