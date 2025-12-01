import orjson
from utils.generation import snowflake
from core import FunctionError
from utils.database import AutoConnection
import typing as t
from schemas import NotificationType, NotificationList, Notification
from utils.generation import generate_id


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
) -> Notification | None:
    if user_id == from_id:
        return None

    db = await conn.create_conn()

    notification_id = str(snowflake.generate())

    await conn.start_transaction()
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

    return notification


async def get_notifications(
    user_id: str,
    conn: AutoConnection,
    cursor: str | None = None,
    limit: int = 20
) -> NotificationList:
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
                 AND p2.is_deleted = FALSE
                 AND c.user_id IS NOT NULL)
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

    return {
        "notifications": notifications,
        "next_cursor": next_cursor,
        "has_more": has_more
    }


async def mark_notification_read(
    user_id: str, notification_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        UPDATE user_notifications
        SET unread = FALSE
        WHERE user_id = $1 AND id = $2
        """, user_id, notification_id
    )


async def mark_all_notifications_read(
    user_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        UPDATE user_notifications
        SET unread = FALSE
        WHERE user_id = $1 AND unread = TRUE
        """, user_id
    )


async def get_unread_notifications_count(
    user_id: str, conn: AutoConnection
) -> int:
    db = await conn.create_conn()
    value = await db.fetchval(
        """
            SELECT COUNT(*)
            FROM user_notifications
            WHERE user_id = $1 AND unread = TRUE
        """,
        user_id
    )
    return value


async def subscribe(
    user_id: str,
    session_id: str,
    subscription: dict,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    await conn.start_transaction()
    await db.execute(
        """
        INSERT INTO webpush_subscriptions (
            id, user_id, session_id, expiration_time, raw
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (session_id) DO UPDATE
        SET updated_at = now(),
            raw = EXCLUDED.raw,
            expiration_time = EXCLUDED.expiration_time
        """,
        str(generate_id()),
        user_id,
        session_id,
        subscription.get("expirationTime"),
        orjson.dumps(subscription).decode()
    )


async def get_subscriptions(
    user_id: str,
    conn: AutoConnection
) -> list[dict[str, t.Any]]:
    db = await conn.create_conn()

    await conn.start_transaction()
    rows = await db.fetch(
        """
        SELECT session_id, expiration_time, raw
        FROM webpush_subscriptions
        WHERE user_id = $1
        """,
        user_id
    )

    subscriptions = []
    for row in rows:
        subscriptions.append(
            {
                "session_id": row["session_id"],
                "expirationTime": row["expiration_time"],
                "raw": row["raw"],
            }
        )

    return subscriptions


async def delete_subscription(
    session_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    await conn.start_transaction()
    await db.execute(
        """
        DELETE FROM webpush_subscriptions
        WHERE session_id = $1
        """,
        session_id
    )
