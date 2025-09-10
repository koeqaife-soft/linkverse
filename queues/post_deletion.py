from core import Global
from utils.database import AutoConnection
from asyncpg import Pool

gb = Global()
pool: Pool = gb.pool


async def cleanup_posts() -> None:
    async with AutoConnection(pool) as conn:
        db = await conn.create_conn()
        async with db.transaction():
            await db.execute(
                """
                DELETE FROM posts
                WHERE is_deleted = TRUE
                      AND deleted_at < NOW() - INTERVAL '3 days'
                """
            )
