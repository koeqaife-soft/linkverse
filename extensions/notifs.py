
import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route
from quart import g
import utils.notifs as notifs
from utils.database import AutoConnection
from utils.realtime import RealtimeManager
import utils.combined as combined
from utils.rate_limiting import rate_limit

bp = Blueprint('notifs', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


@route(bp, "/users/me/notifications", methods=["GET"])
@rate_limit(60, 60)
async def get_notifications() -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    preload = params.get("preload", False)
    limit = params.get("limit", 20)

    async with AutoConnection(pool) as conn:
        result = await notifs.get_notifications(g.user_id, conn, cursor, limit)
        notifications = result.data.get("notifications", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "notifications"}
        if preload:
            preloaded = []
            for object in notifications:
                _result = await combined.preload_notification(
                    g.user_id, conn, object
                )
                preloaded.append(_result.data)
            response_data.update({"notifications": preloaded})
        else:
            response_data.update({"notifications": notifications})
    return response(data=response_data, cache=True), 200


@route(bp, "/users/me/notifications/unread", methods=["GET"])
@rate_limit(300, 60)
async def get_unread_notifications_count() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await notifs.get_unread_notifications_count(g.user_id, conn)
        count = result.data
    return response(data={"count": count}, cache=True), 200


@route(bp, "/users/me/notifications/<id>/read", methods=["POST"])
@rate_limit(30, 60)
async def read_notification(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await notifs.mark_notification_read(g.user_id, id, conn)
        unread_count = await notifs.get_unread_notifications_count(
            g.user_id, conn
        )

    await rt_manager.publish_event(
        g.user_id, "notification_read",
        {"id": id, "unread": unread_count.data}
    )
    return response(is_empty=True), 204


@route(bp, "/users/me/notifications/read", methods=["POST"])
@rate_limit(15, 60)
async def read_all_notifications() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await notifs.mark_all_notifications_read(g.user_id, conn)

    await rt_manager.publish_event(
        g.user_id, "notification_read", {}
    )
    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
