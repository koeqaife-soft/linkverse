import typing as t
from enum import Enum
from core import Status
from utils.database import AutoConnection
from utils.generation import snowflake


class NotificationType(str, Enum):
    NEW_COMMENT = "new_comment"
    FOLLOWED = "followed"


class Notification(t.TypedDict):
    type: str
    from_id: str
    message: str | None
    linked_type: str | None
    linked_id: str | None
    second_linked_id: str | None


async def create_notification(
    user_id: str,
    from_id: str,
    type: NotificationType | str,
    conn: AutoConnection,
    message: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    second_linked_id: str | None = None
) -> Status[None]:
    if user_id == from_id:
        return

    db = await conn.create_conn()

    notification_id = str(snowflake.generate())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO user_notifications (
                id, user_id, type, message, from_id,
                linked_type, linked_id, second_linked_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            """,
            notification_id, user_id, type, message, from_id,
            linked_type, linked_id, second_linked_id
        )
