import asyncpg


async def create_pool(**config) -> asyncpg.pool.Pool:
    pool = await asyncpg.create_pool(
        **config,
        min_size=2,
        max_size=10
    )
    if pool is None:
        raise
    return pool


async def initialize_database(db: asyncpg.Connection):
    async with db.transaction():
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    avatar_url TEXT
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS auth_keys (
                    auth_key_id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token_secret TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                    ON DELETE CASCADE
                );
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id ON auth_keys(user_id);
            """)
        except asyncpg.PostgresError as e:
            print(f"Database error: {e}")
            raise
