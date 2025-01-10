import asyncpg
from quart import Blueprint, Quart, Response, request
from core import FunctionError, response, Global, route
from quart import g
import utils.users as users
import utils.posts as posts
from utils.cache import users as cache_users
from utils.database import AutoConnection

bp = Blueprint('users', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/users/me", methods=["GET"])
async def get_profile_me() -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)

    return response(data=user.data.dict, cache=True), 200


@route(bp, "/users/me", methods=["PATCH"])
async def update_profile_me() -> tuple[Response, int]:
    data = g.data
    user_id = g.user_id
    if not data:
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with AutoConnection(pool) as conn:
        await users.update_user(user_id, data, conn)

    await cache_users.delete_user_cache(user_id)

    return response(), 204


async def validate_post_or_comment(
    post_id: str, comment_id: str | None,
    conn: AutoConnection
) -> None:
    if comment_id:
        await posts.get_comment(post_id, comment_id, conn)
    else:
        await posts.get_post(post_id, conn)


@route(bp, "/users/me/favorites", methods=["POST"])
async def add_favorite() -> tuple[Response, int]:
    data = g.data
    post_id = data.get("post_id")
    comment_id = data.get("comment_id")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await validate_post_or_comment(post_id, comment_id, conn)
        await users.add_to_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


@route(bp, "/users/me/favorites", methods=["DELETE"])
async def rem_favorite() -> tuple[Response, int]:
    post_id = request.args.get("post_id")
    comment_id = request.args.get("comment_id")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await validate_post_or_comment(post_id, comment_id, conn)
        await users.rem_from_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


async def _preload_favorites(
    favorites: list[dict], conn: AutoConnection
) -> tuple[list[dict], list[dict]]:
    posts_data: list[dict] = []
    comments_data: list[dict] = []
    errors: list[tuple[str, str, str]] = []

    for fav in favorites:
        try:
            if fav["comment_id"]:
                comment = await posts.get_comment(
                    fav["post_id"], fav["comment_id"], conn
                )
                comments_data.append(comment.data.to_dict())
            else:
                post = await posts.get_post(fav["post_id"], conn)
                posts_data.append(post.data.to_dict())
        except FunctionError as e:
            if e.message in {"COMMENT_DOES_NOT_EXIST", "POST_DOES_NOT_EXIST"}:
                await users.rem_from_favorites(
                    g.user_id, conn, fav["post_id"], fav["comment_id"]
                )
                errors.append((fav["post_id"], fav["comment_id"], e.message))

    return posts_data, comments_data, errors


@route(bp, "/users/me/favorites", methods=["GET"])
async def get_favorites() -> tuple[Response, int]:
    cursor = request.args.get("cursor", None)
    type = request.args.get("type", None)
    preload = request.args.get("preload", "false").lower() == "true"

    async with AutoConnection(pool) as conn:
        result = await users.get_favorites(g.user_id, conn, cursor, type)

        favorites = result.data.get("favorites", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "favorites"}

        if preload:
            posts_data, comments_data, errors = await _preload_favorites(
                favorites, conn
            )
            if posts_data:
                response_data.update({"posts": posts_data})
            if comments_data:
                response_data.update({"comments": comments_data})
            if errors:
                response_data.update({"errors": errors})

    return response(data=response_data, cache=True), 200


@route(bp, "/users/<user_id>", methods=["GET"])
async def get_profile(user_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)

    return response(data=user.data.dict, cache=True), 200


def load(app: Quart):
    app.register_blueprint(bp)
