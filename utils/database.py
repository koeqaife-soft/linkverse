import aiosqlite


class Transaction:
    def __init__(
        self, connection: aiosqlite.Connection,
        manual_commit: bool = False
    ):
        self.connection = connection
        self.manual_commit = manual_commit
        self._transaction_started = False

    async def __aenter__(self):
        if not self._transaction_started:
            await self.connection.execute("BEGIN;")
            self._transaction_started = True
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._transaction_started:
            if exc_type is None:
                if not self.manual_commit:
                    await self.connection.commit()
            else:
                await self.connection.rollback()
        self._transaction_started = False


async def initialize_database(db: aiosqlite.Connection):
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
    await db.commit()
