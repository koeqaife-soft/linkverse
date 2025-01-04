import asyncpg
from quart import Blueprint, Quart, Response, request
from core import response, Global, route
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

    return response(data=user.data.dict), 200


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


@route(bp, "/users/me/favorites", methods=["POST"])
async def add_favorite() -> tuple[Response, int]:
    data = g.data
    post_id = data.get("post_id")
    comment_id = data.get("comment_id")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await posts.get_post(post_id, conn)
        await users.add_to_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


@route(bp, "/users/me/favorites", methods=["DELETE"])
async def rem_favorite() -> tuple[Response, int]:
    post_id = request.args.get("post_id")
    comment_id = request.args.get("comment_id")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await posts.get_post(post_id, conn)
        await users.rem_from_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


@route(bp, "/users/<user_id>", methods=["GET"])
async def get_profile(user_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)

    return response(data=user.data.dict), 200


def load(app: Quart):
    app.register_blueprint(bp)
