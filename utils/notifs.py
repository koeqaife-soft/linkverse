from utils.generation import snowflake
from core import Status, FunctionError
from utils.database import AutoConnection
import typing as t
from schemas import NotificationType, NotificationList, Notification


async def create_notification(
    user_id: str,
    from_id: str,
    type: NotificationType | str,
    conn: AutoConnection,
    message: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    second_linked_id: str | None = None,
    unread: bool = True
) -> Status[Notification]:
    if user_id == from_id:
        return Status(True)

    db = await conn.create_conn()

    notification_id = str(snowflake.generate())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO user_notifications (
                id, user_id, type, message, from_id,
                linked_type, linked_id, second_linked_id,
                unread
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9
            )
            """,
            notification_id, user_id, type, message, from_id,
            linked_type, linked_id, second_linked_id, unread
        )

    notification = Notification({
        "id": notification_id,
        "from_id": from_id,
        "message": message,
        "type": type,
        "linked_type": linked_type,
        "linked_id": linked_id,
        "second_linked_id": second_linked_id,
        "unread": unread
    })

    return Status(True, data=notification)


async def get_notifications(
    user_id: str,
    conn: AutoConnection,
    cursor: str | None = None,
    limit: int = 20
) -> Status[NotificationList]:
    db = await conn.create_conn()
    query = """
        SELECT n.id,
            n.type,
            n.message,
            n.from_id,
            n.linked_type,
            n.linked_id,
            n.second_linked_id,
            n.unread
        FROM user_notifications n
        LEFT JOIN posts p1
            ON n.linked_type = 'post'
            AND n.linked_id = p1.post_id
        LEFT JOIN posts p2
            ON n.linked_type = 'comment'
            AND n.second_linked_id = p2.post_id
        LEFT JOIN comments c
            ON n.linked_type = 'comment'
            AND n.linked_id = c.comment_id
        WHERE n.user_id = $1
        AND (
                (n.linked_type = 'post'
                 AND p1.is_deleted = FALSE)
            OR  (n.linked_type = 'comment'
                 AND p2.is_deleted = FALSE)
            OR  (n.linked_type NOT IN ('post', 'comment'))
        )
    """
    params: list[t.Any] = [user_id]

    if cursor:
        query += " AND n.id < $2"
        params.append(cursor)

    query += f" ORDER BY n.id::bigint DESC LIMIT {limit + 1}"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_NOTIFS", 200, None)

    has_more = len(rows) > limit
    rows = rows[:limit]

    notifications = [
        Notification({
            "id": row["id"],
            "type": row["type"],
            "message": row["message"],
            "from_id": row["from_id"],
            "linked_type": row["linked_type"],
            "linked_id": row["linked_id"],
            "second_linked_id": row["second_linked_id"],
            "unread": row["unread"]
        })
        for row in rows
    ]

    last_row = rows[-1]

    next_cursor = last_row["id"]

    return Status(
        True,
        data={
            "notifications": notifications,
            "next_cursor": next_cursor,
            "has_more": has_more
        }
    )


async def mark_notification_read(
    user_id: str, notification_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE user_notifications
            SET unread = FALSE
            WHERE user_id = $1 AND id = $2
            """, user_id, notification_id
        )
    return Status(True)


async def mark_all_notifications_read(
    user_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE user_notifications
            SET unread = FALSE
            WHERE user_id = $1 AND unread = TRUE
            """, user_id
        )
    return Status(True)


async def get_unread_notifications_count(
    user_id: str, conn: AutoConnection
) -> Status[int]:
    db = await conn.create_conn()
    value = await db.fetchval(
        """
            SELECT COUNT(*)
            FROM user_notifications
            WHERE user_id = $1 AND unread = TRUE
        """,
        user_id
    )
    return Status(True, value)
