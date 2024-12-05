import asyncpg
from quart import Blueprint, Quart, Response, request
from core import response, Global, route, FunctionError
from quart import g
import utils.posts as posts
from utils.cache import users as cache_users
from utils.cache import posts as cache_posts
from utils.database import AutoConnection
import utils.posts_list as posts_list

bp = Blueprint('posts', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/posts/popular", methods=["GET"])
async def popular_posts() -> tuple[Response, int]:
    data = g.data
    show_viewed = data.get("show_viewed")
    offset = data.get("offset")
    limit = data.get("limit") or 50

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_popular_posts(
            g.user_id, conn, limit, offset, show_viewed
        )

    return response(data=result.data), 200


@route(bp, "/posts/new", methods=["GET"])
async def new_posts() -> tuple[Response, int]:
    data = g.data
    show_viewed = data.get("show_viewed")
    offset = data.get("offset")
    limit = data.get("limit") or 50

    async with AutoConnection(pool) as conn:
        result = await posts_list.get_new_posts(
            g.user_id, conn, limit, offset, show_viewed
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
        result = await cache_posts.get_post(id, conn)

        user = await cache_users.get_user(result.data.user_id, conn, True)

        reaction = await posts.get_reaction(g.user_id, id, None, conn)

    data = result.data.to_dict()
    if user.data is not None:
        data["user"] = user.data.dict
    if reaction.data is not None:
        data["is_like"] = reaction.data

    return response(data=data), 200


@route(bp, "/posts/batch", methods=["GET"])
async def get_posts_batch() -> tuple[Response, int]:
    posts_param = request.args.get('posts', "")
    _posts = posts_param.split(',')

    _data = []
    errors = []

    async with AutoConnection(pool) as conn:
        for post in _posts:
            try:
                result = await cache_posts.get_post(str(post), conn)
            except FunctionError as e:
                errors.append({"post": post, "error_msg": e.message})
                continue

            user = await cache_users.get_user(result.data.user_id, conn, True)

            reaction = await posts.get_reaction(g.user_id, post, None, conn)

            _temp = result.data.to_dict()

            if user.data is not None:
                _temp["user"] = user.data.dict
            if reaction.data is not None:
                _temp["is_like"] = reaction.data

            _data.append(_temp)

    if errors:
        return response(error=True, data={"errors": errors}), 400

    return response(data={"posts": _data}), 200


@route(bp, "/posts/<id>", methods=["DELETE"])
async def delete_post(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        post = await cache_posts.get_post(id, conn)

        if post.data.user_id != g.user_id:
            return response(error=True, error_msg="FORBIDDEN"), 403

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
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with AutoConnection(pool) as conn:
        post = await posts.get_post(id, conn)

        if post.data.user_id != g.user_id:
            return response(error=True, error_msg="FORBIDDEN"), 403

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
        await cache_posts.get_post(id, conn)
        result = await posts.create_comment(g.user_id, id, content, conn)

    return response(data=result.data.to_dict()), 201


@route(bp, "/posts/<id>/comments", methods=["GET"])
async def get_comments(id: str) -> tuple[Response, int]:
    cursor = request.args.get("cursor", None)

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)

        result = await posts.get_comments(id, cursor, g.user_id, conn)

        users = {}
        comments = []

        for comment in result.data["comments"]:
            reaction = await posts.get_reaction(
                g.user_id, None, comment.comment_id, conn
            )

            if comment.user_id not in users:
                try:
                    user_data = await cache_users.get_user(
                        comment.user_id, conn, True
                    )
                    users[comment.user_id] = user_data.data.dict
                except FunctionError as e:
                    if e.code != 404:
                        raise e

            _temp = comment.to_dict()
            if reaction.data is not None:
                _temp["is_like"] = reaction.data

            comments.append(_temp)

    _data = result.data | {"users": users, "comments": comments}
    return response(data=_data), 200


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["POST"])
async def comment_add_reaction(id: str, cid: str) -> tuple[Response, int]:
    data = g.data
    is_like: bool = data.get("is_like")

    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.get_comment(id, cid, conn)
        await posts.add_reaction(g.user_id, is_like, None, cid, conn)

    return response(), 204


@route(bp, "/posts/<id>/comments/<cid>/reactions", methods=["DELETE"])
async def comment_rem_reaction(id: str, cid: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_posts.get_post(id, conn)
        await posts.get_comment(id, cid, conn)
        await posts.rem_reaction(g.user_id, None, cid, conn)

    return response(), 204


@route(bp, "/users/<user_id>/posts", methods=["GET"])
async def get_user_posts(user_id: str) -> tuple[Response, int]:
    cursor = request.args.get("cursor", None)
    sort = request.args.get("sort", None)

    async with AutoConnection(pool) as conn:
        await cache_users.get_user(user_id, conn, True)
        user_posts = await posts.get_user_posts(user_id, cursor, conn, sort)
        _posts = [post.to_dict() for post in user_posts.data["posts"]]
        user_posts.data["posts"] = _posts

    return response(data=user_posts.data), 200


def load(app: Quart):
    app.register_blueprint(bp)
