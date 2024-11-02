import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, error_response
from quart import g
import utils.posts as posts
from utils.cache import users as cache_users
from utils.cache import posts as cache_posts
from utils.cache import AutoConnection
import utils.posts_list as posts_list

bp = Blueprint('posts', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/posts", methods=["POST"])
async def create_post() -> tuple[Response, int]:
    data = g.data
    content: str = data.get('content')
    tags: list[str] = data.get("tags", [])
    media: list[str] = data.get("media", [])

    async with pool.acquire() as db:
        result = await posts.create_post(g.user_id, content, db, tags, media)

    if not result.success:
        return error_response(result), 500

    return response(data=result.data or {}), 201


@route(bp, "/posts/popular", methods=["GET"])
async def popular_posts() -> tuple[Response, int]:
    data = g.data
    show_viewed = data.get("show_viewed")
    offset = data.get("offset")
    limit = data.get("limit")

    async with pool.acquire() as db:
        result = await posts_list.get_popular_posts(
            g.user_id, db, limit, offset, show_viewed
        )

    if not result.success:
        return error_response(result), 500

    assert result.data is not None

    return response(data=result.data), 200


@route(bp, "/posts/view", methods=["POST"])
async def view_posts() -> tuple[Response, int]:
    data = g.data
    posts = data["posts"]
    user_id = g.user_id

    async with pool.acquire() as db:
        result = await posts_list.mark_posts_as_viewed(user_id, posts, db)

    if not result.success:
        return error_response(result), 400

    assert result.data is not None

    return response(), 204


@route(bp, "/posts/<int:id>", methods=["GET"])
async def get_post(id: int) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await cache_posts.get_post(id, conn)

        if not result.success:
            return error_response(result), 400
        assert result.data is not None

        user = await cache_users.get_user(result.data.user_id, conn)

    data = result.data.to_dict()
    if user.data is not None:
        data["user"] = user.data.dict

    return response(data=data), 200


@route(bp, "/posts/<int:id>", methods=["DELETE"])
async def delete_post(id: int) -> tuple[Response, int]:
    async with pool.acquire() as db:
        post = await cache_posts.get_post(id, db)
        if not post.success:
            return error_response(post), 400
        if post.data.user_id != g.user_id:  # type: ignore
            return response(error=True, error_msg="FORBIDDEN"), 403
        result = await posts.delete_post(id, db)

    await cache_posts.remove_post_cache(id)

    if not result.success:
        return error_response(result), 500

    return response(), 204


@route(bp, "/posts/<int:id>", methods=["PATCH"])
async def update_post(id: int) -> tuple[Response, int]:
    data = g.data
    content: str | None = data.get("content")
    tags: list[str] | None = data.get("tags")
    media: list[str] | None = data.get("media")

    if content is None and tags is None and media is None:
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with pool.acquire() as db:
        post = await posts.get_post(id, db)
        if not post.success:
            return error_response(post), 400
        if post.data.user_id != g.user_id:  # type: ignore
            return response(error=True, error_msg="FORBIDDEN"), 403
        result = await posts.update_post(id, content, tags, media, db)

    await cache_posts.remove_post_cache(id)

    if not result.success:
        return error_response(result), 500

    return response(), 204


@route(bp, "/posts/<int:id>/reactions", methods=["POST"])
async def add_reaction(id: int) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with pool.acquire() as db:
        post = await posts.get_post(id, db)
        if not post.success:
            return error_response(post), 400
        result = await posts.add_reaction(g.user_id, is_like, id, db)

    if not result.success:
        return error_response(result), 500

    return response(), 204


@route(bp, "/posts/<int:id>/reactions", methods=["DELETE"])
async def rem_reaction(id: int) -> tuple[Response, int]:
    async with pool.acquire() as db:
        post = await posts.get_post(id, db)
        if not post.success:
            return error_response(post), 400
        result = await posts.rem_reaction(g.user_id, id, db)

    if not result.success:
        return error_response(result), 500

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
