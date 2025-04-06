import time
import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
import utils.posts as posts
from utils.cache import posts as cache_posts
from utils.database import AutoConnection
import utils.posts_list as posts_list
from utils.realtime import RealtimeManager
from utils.users import NotificationType
import utils.combined as combined

bp = Blueprint('posts', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


@route(bp, "/posts/following", methods=["GET"])
async def posts_by_following() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 50)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_posts_by_following(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result.data), 200


@route(bp, "/posts/popular", methods=["GET"])
async def popular_posts() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 50)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_popular_posts(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result.data), 200


@route(bp, "/posts/new", methods=["GET"])
async def new_posts() -> tuple[Response, int]:
    params: dict = g.params
    hide_viewed = params.get("hide_viewed", True)
    cursor = params.get("cursor")
    limit = params.get("limit", 50)

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_new_posts(
            g.user_id, conn, limit, cursor, hide_viewed
        )

    return response(data=result.data), 200


@route(bp, "/posts/view", methods=["POST"])
async def view_posts() -> tuple[Response, int]:
    data = g.data
    posts = data["posts"]
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await posts_list.mark_posts_as_viewed(user_id, posts, conn)

    return response(), 204


@route(bp, "/posts", methods=["POST"])
async def create_post() -> tuple[Response, int]:
    data = g.data
    content: str = data.get('content')
    tags: list[str] = data.get("tags", [])
    media: list[str] = data.get("media", [])

    async with AutoConnection(pool) as conn:
        result = await posts.create_post(g.user_id, content, conn, tags, media)

    return response(data=result.data or {}), 201


@route(bp, "/posts/<id>", methods=["GET"])
async def get_post(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await combined.get_full_post(g.user_id, id, conn)

    return response(data=result.data, cache=True), 200


@route(bp, "/posts/batch", methods=["GET"])
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

            _data.append(result.data)

    if errors:
        return response(error=True, data={"errors": errors}), 400

    return response(data={"posts": _data}, cache=True), 200


@route(bp, "/posts/<id>", methods=["DELETE"])
async def delete_post(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        post = await cache_posts.get_post(id, conn)

        if post.data.user_id != g.user_id:
            raise FunctionError("FORBIDDEN", 403, None)

        await posts.delete_post(id, conn)

    await cache_posts.remove_post_cache(id)

    return response(), 204


@route(bp, "/posts/<id>", methods=["PATCH"])
async def update_post(id: str) -> tuple[Response, int]:
    data = g.data
    content: str | None = data.get("content")
    tags: list[str] | None = data.get("tags")
    media: list[str] | None = data.get("media")

    if content is None and tags is None and media is None:
        raise FunctionError("INCORRECT_DATA", 400, None)

    now = time.time()

    async with AutoConnection(pool) as conn:
        post = await posts.get_post(id, conn)

        if (
            post.data.user_id != g.user_id or
            now - post.data.created_at_unix > 86400
        ):
            raise FunctionError("FORBIDDEN", 403, None)

        await posts.update_post(id, content, tags, media, conn)

    await cache_posts.remove_post_cache(id)

    return response(), 204


@route(bp, "/posts/<id>/reactions", methods=["POST"])
async def add_reaction(id: str) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.add_reaction(g.user_id, is_like, id, None, conn)

    return response(), 204


@route(bp, "/posts/<id>/reactions", methods=["DELETE"])
async def rem_reaction(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.rem_reaction(g.user_id, id, None, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments", methods=["POST"])
async def create_comment(id: str) -> tuple[Response, int]:
    data = g.data
    content = data.get("content")

    async with AutoConnection(pool) as conn:
        post = await cache_posts.get_post(id, conn)
        result = await posts.create_comment(g.user_id, id, content, conn)
        await rt_manager.publish_notification(
            g.user_id, post.data.user_id, NotificationType.NEW_COMMENT,
            conn, None, "comment",
            result.data.comment_id,
            result.data.post_id,
            result.data.dict
        )

    return response(data=result.data.dict), 201


@route(bp, "/posts/<id>/comments/<cid>", methods=["DELETE"])
async def delete_comment(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        comment = await posts.get_comment(id, cid, conn)
        if comment.data.user_id != g.user_id:
            raise FunctionError("FORBIDDEN", 403, None)

        await posts.delete_comment(id, cid, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments/<cid>", methods=["GET"])
async def get_comment(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)

        comment = await combined.get_full_comment(
            g.user_id, id, cid, conn
        )

    return response(data=comment.data, cache=True), 200


@route(bp, "/posts/<id>/comments", methods=["GET"])
async def get_comments(id: str) -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)

        result = await posts.get_comments(id, cursor, g.user_id, conn)

        users = {}
        comments = []

        for comment in result.data["comments"]:
            _temp = await combined.get_full_comment(
                g.user_id, id, comment.comment_id,
                conn, users, comment.dict
            )

            comments.append(_temp.data)

    _data = result.data | {"users": users, "comments": comments}
    return response(data=_data, cache=True), 200


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["POST"])
async def comment_add_reaction(id: str, cid: str) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.get_comment(id, cid, conn)
        await posts.add_reaction(g.user_id, is_like, id, cid, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["DELETE"])
async def comment_rem_reaction(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.get_comment(id, cid, conn)
        await posts.rem_reaction(g.user_id, id, cid, conn)

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
