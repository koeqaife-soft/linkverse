import time
import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
from realtime.notifs import publish_notification
import utils.posts as posts
from utils.cache import posts as cache_posts
from utils.database import AutoConnection
import utils.posts_list as posts_list
import utils.combined as combined
from utils.storage import get_context
from utils.rate_limiting import rate_limit
from utils.users import Permission, check_permission
from utils.moderation import create_log, log_metadata
from schemas import NotificationType

bp = Blueprint('posts', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool


@route(bp, "/posts/following", methods=["GET"])
@rate_limit(30, 60)
async def posts_by_following() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 300)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_posts_by_following(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result), 200


@route(bp, "/posts/popular", methods=["GET"])
@rate_limit(30, 60)
async def popular_posts() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 300)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_popular_posts(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result), 200


@route(bp, "/posts/new", methods=["GET"])
@rate_limit(30, 60)
async def new_posts() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 300)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_new_posts(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result), 200


@route(bp, "/posts/view", methods=["POST"])
@rate_limit(6000, 60, 300, 60)
async def view_posts() -> tuple[Response, int]:
    data = g.data
    posts = data["posts"]
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await posts_list.mark_posts_as_viewed(user_id, posts, conn)

    return response(), 204


@route(bp, "/posts", methods=["POST"])
@rate_limit(20, 60)
async def create_post() -> tuple[Response, int]:
    data = g.data
    content: str = data.get('content')
    tags: list[str] = data.get("tags", [])
    ctags: list[str] = data.get("ctags", [])
    file_context_id = data.get("file_context_id")

    async with AutoConnection(pool) as conn:
        if file_context_id:
            await get_context(file_context_id, conn)

        result = await posts.create_post(
            g.user_id, content, conn, tags, file_context_id, ctags
        )

    return response(data=result or {}), 201


@route(bp, "/posts/<id>", methods=["GET"])
@rate_limit(60, 60)
async def get_post(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await combined.get_full_post(g.user_id, id, conn)

    return response(data=result, cache=True), 200


@route(bp, "/posts/batch", methods=["GET"])
@rate_limit(60, 60)
async def get_posts_batch() -> tuple[Response, int]:
    params: dict = g.params
    _posts = params.get('posts', [])

    _data = []
    errors = []

    async with AutoConnection(pool) as conn:
        for post in _posts:
            try:
                result = await combined.get_full_post(g.user_id, post, conn)
            except FunctionError as e:
                errors.append({"post": post, "error_msg": e.message})
                continue

            _data.append(result)

    if errors:
        return response(error=True, data={"errors": errors}), 400

    return response(data={"posts": _data}, cache=True), 200


@route(bp, "/posts/<id>", methods=["DELETE"])
@rate_limit(60, 60)
async def delete_post(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        post = await cache_posts.get_post(id, conn)

        if post.user_id != g.user_id:
            permission_available = await check_permission(
                g.user_id, Permission.MODERATE_POSTS, conn
            )
            reason = g.params.get("reason")
            if not permission_available or not reason:
                raise FunctionError("FORBIDDEN", 403, None)
            else:
                await posts.delete_post(id, conn)
                log_id = await create_log(
                    g.user_id, post.user_id,
                    log_metadata(), post.dict,
                    "post", post.post_id,
                    "delete_post", reason,
                    conn
                )
                await publish_notification(
                    g.user_id, post.user_id,
                    NotificationType.MOD_DELETED_POST,
                    conn,
                    linked_type="mod_audit",
                    linked_id=log_id,
                    message=reason
                )
        else:
            await posts.delete_post(id, conn)

    await cache_posts.remove_post_cache(id)

    return response(), 204


@route(bp, "/posts/<id>", methods=["PATCH"])
@rate_limit(20, 60)
async def update_post(id: str) -> tuple[Response, int]:
    data = g.data
    content: str | None = data.get("content")
    tags: list[str] | None = data.get("tags")

    if content is None and tags is None:
        raise FunctionError("INCORRECT_DATA", 400, None)

    now = time.time()

    async with AutoConnection(pool) as conn:
        post = await posts.get_post(id, conn)

        if (
            post.user_id != g.user_id or
            now - post.created_at_unix > 86400
        ):
            raise FunctionError("FORBIDDEN", 403, None)

        await posts.update_post(id, content, tags, conn)

    await cache_posts.remove_post_cache(id)

    return response(), 204


@route(bp, "/posts/<id>/reactions", methods=["POST"])
@rate_limit(30, 60)
async def add_reaction(id: str) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.add_reaction(g.user_id, is_like, id, None, conn)

    return response(), 204


@route(bp, "/posts/<id>/reactions", methods=["DELETE"])
@rate_limit(30, 60)
async def rem_reaction(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.rem_reaction(g.user_id, id, None, conn)

    return response(), 204


@route(bp, "/tags/<name>/posts", methods=["GET"])
@rate_limit(30, 60)
async def get_tag_posts(name: str) -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor")
    limit = params.get("limit", 50)

    async with AutoConnection(pool) as conn:
        tag = await posts.get_tag(name, conn)
        id = tag.tag_id
        _posts = await posts_list.get_tag_posts(id, conn, limit, cursor)

    return response(data=_posts), 200


@route(bp, "/tags/<name>", methods=["GET"])
@rate_limit(30, 60)
async def get_tag(name: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        tag = await posts.get_tag(name, conn)

    return response(data=tag.dict), 200


def load(app: Quart):
    app.register_blueprint(bp)
