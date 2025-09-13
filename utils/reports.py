from utils.database import AutoConnection
from core import Status
from utils.generation import generate_id


async def create_report(
    user_id: int,
    target_id: str,
    target_type: str,
    reason: str,
    conn: AutoConnection
) -> Status[str]:
    db = await conn.create_conn()
    new_id = str(generate_id())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO reports
            (report_id, user_id, target_id, target_type, reason)
            VALUES ($1, $2, $3, $4, $5)
            """, new_id, user_id, target_id, target_type, reason
        )

    return Status(True, data=new_id)
