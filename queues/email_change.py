from core import Global
from utils.database import AutoConnection
from asyncpg import Pool

gb = Global()
pool: Pool = gb.pool


async def confirm_pending_emails(batch_size: int = 1000) -> bool:
    async with AutoConnection(pool) as conn:
        db = await conn.create_conn()
        async with db.transaction():
            updated_rows = await db.fetch(
                """
                WITH to_update AS (
                    SELECT user_id
                    FROM users
                    WHERE pending_email IS NOT NULL
                    AND pending_email_until > NOW()
                    LIMIT $1
                )
                UPDATE users u
                SET email = pending_email,
                    pending_email = NULL,
                    pending_email_until = NULL
                FROM to_update t
                WHERE u.user_id = t.user_id
                RETURNING u.user_id
                """,
                batch_size,
            )
            return len(updated_rows) != 0
