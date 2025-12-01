from utils.database import AutoConnection
from utils.generation import generate_id


async def create_report(
    user_id: int,
    target_id: str,
    target_type: str,
    reason: str,
    conn: AutoConnection
) -> str:
    db = await conn.create_conn()
    new_id = str(generate_id())

    await conn.start_transaction()
    await db.execute(
        """
        INSERT INTO reports
        (report_id, user_id, target_id, target_type, reason)
        VALUES ($1, $2, $3, $4, $5)
        """, new_id, user_id, target_id, target_type, reason
    )

    return new_id


async def mark_all_reports_as(
    status: str,
    target_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    await conn.start_transaction()
    await db.execute(
        """
        UPDATE reports
        SET status = $1
        WHERE target_id = $2
        """, status, target_id
    )


async def get_reports(
    target_id: str,
    conn: AutoConnection,
    limit: int = 100,
    offset: int = 0,
    with_status: str = "pending"
) -> list[dict]:
    db = await conn.create_conn()

    rows = await db.fetch(
        """
        SELECT *
        FROM reports
        WHERE target_id = $1 AND status = $2
        OFFSET $3
        LIMIT $4
        """, target_id, with_status, offset, limit
    )
    if not rows:
        return []

    return [
        dict(row)
        for row in rows
        if row
    ]
