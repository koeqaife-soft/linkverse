

import asyncio
from core import remove_none_values
from queues.web_push import enqueue_push
from schemas import NotificationType
from utils import combined, notifs
from utils.database import AutoConnection
from utils.cache import users as cache_users
from realtime.broker import publish_event


async def publish_notification(
    user_id: str,
    to: str,
    type: NotificationType | str,
    conn: AutoConnection,
    message: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    second_linked_id: str | None = None,
    loaded: dict | None = None,
    unread: bool = True
) -> None:
    if user_id == to:
        return
    if loaded:
        message = None

    notification = await notifs.create_notification(
        to, user_id, type, conn, message,
        linked_type, linked_id, second_linked_id,
        unread
    )
    notification["loaded"] = loaded  # type: ignore
    notification = await combined.preload_notification(
        user_id, conn, notification
    )
    notification = remove_none_values(notification)

    from_user = await cache_users.get_user(user_id, conn, True)

    async def _task():
        await publish_event(
            f"user:{to}",
            {
                "type": "user",
                "event": "notification",
                "data": notification
            }
        )
        loaded = notification.get("loaded")
        content: str | None = None

        if loaded:
            content = loaded.get("content")

        if not content:
            content = message

        payload = {
            "avatar_url": from_user.avatar_url,
            "id": notification["id"],
            "message": content,
            "type": type,
            "username": (
                from_user.display_name
                or from_user.username
            )
        }
        if notification["loaded"].get("parent_comment_id"):
            payload["is_reply"] = True

        await enqueue_push(to, payload)
    asyncio.create_task(_task())
