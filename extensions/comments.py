import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
import utils.posts as posts
import utils.comments as comments
from utils.cache import posts as cache_posts
from utils.database import AutoConnection
from utils.realtime import RealtimeManager
import utils.combined as combined
from schemas import NotificationType
from utils.rate_limiting import rate_limit
from utils.users import Permission, check_permission
from utils.moderation import create_log, log_metadata

bp = Blueprint('comments', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


@route(bp, "/posts/<id>/comments", methods=["POST"])
@rate_limit(20, 60, 5, 30)
async def create_comment(id: str) -> tuple[Response, int]:
    data = g.data
    content = data.get("content")
    type = data.get("type")
    parent_id = data.get("parent_id")

    async with AutoConnection(pool) as conn:
        post = await cache_posts.get_post(id, conn)
        notif_to = post.data.user_id
        if type == "update" and post.data.user_id != g.user_id:
            raise FunctionError("FORBIDDEN", 403, None)

        if parent_id:
            comment = await comments.get_comment(id, parent_id, conn)
            notif_to = comment.data.user_id

        result = await comments.create_comment(
            g.user_id, id, content, conn, type, parent_id
        )
        await rt_manager.publish_notification(
            g.user_id, notif_to, NotificationType.NEW_COMMENT,
            conn, None, "comment",
            result.data.comment_id,
            result.data.post_id,
            result.data.dict
        )

    return response(data=result.data.dict), 201


@route(bp, "/posts/<id>/comments/<cid>", methods=["DELETE"])
@rate_limit(100, 60)
async def delete_comment(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        comment = await comments.get_comment(id, cid, conn)
        if comment.data.user_id != g.user_id:
            permission_available = await check_permission(
                g.user_id, Permission.MODERATE_COMMENTS, conn
            )
            reason = g.params.get("reason")
            if not permission_available.data or not reason:
                raise FunctionError("FORBIDDEN", 403, None)
            else:
                await comments.delete_comment(id, cid, conn)
                log_id = await create_log(
                    g.user_id, comment.data.user_id,
                    log_metadata().data, comment.data.dict,
                    "comment", comment.data.comment_id,
                    "delete_comment", reason,
                    conn
                )
                await rt_manager.publish_notification(
                    g.user_id, comment.data.user_id,
                    NotificationType.MOD_DELETED_COMMENT,
                    conn,
                    linked_type="mod_audit",
                    linked_id=log_id.data,
                    message=reason
                )
        else:
            await comments.delete_comment(id, cid, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments/<cid>", methods=["GET"])
@rate_limit(60, 60)
async def get_comment(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)

        comment = await combined.get_full_comment(
            g.user_id, id, cid, conn
        )

    return response(data=comment.data, cache=True), 200


@route(bp, "/posts/<id>/comments", methods=["GET"])
@rate_limit(60, 60)
async def get_comments(id: str) -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    type = params.get("type", None)
    parent_id = params.get("parent_id", None)

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)

        result = await comments.get_comments(
            id, cursor, g.user_id, conn, type, parent_id
        )

        users: dict[str, dict] = {}
        _comments = []

        for comment in result.data["comments"]:
            _temp = await combined.get_full_comment(
                g.user_id, id, comment.comment_id,
                conn, users, comment.dict
            )

            _comments.append(_temp.data)

    _data = result.data | {"users": users, "comments": _comments}
    return response(data=_data, cache=True), 200


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["POST"])
@rate_limit(30, 60)
async def comment_add_reaction(id: str, cid: str) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await comments.get_comment(id, cid, conn)
        await posts.add_reaction(g.user_id, is_like, id, cid, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["DELETE"])
@rate_limit(30, 60)
async def comment_rem_reaction(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await comments.get_comment(id, cid, conn)
        await posts.rem_reaction(g.user_id, id, cid, conn)

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
