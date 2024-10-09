import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, error_response, route
from quart import g
import utils.users as users
from utils.cache import users as cache_users

bp = Blueprint('users', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/users/me", methods=["GET"])
async def get_profile_me() -> tuple[Response, int]:
    user_id = g.user_id

    user = await cache_users.get_user(user_id, pool)
    if not user.success:
        return error_response(user), 500

    assert user.data is not None
    return response(data=user.data.dict), 200


@route(bp, "/users/me", methods=["PATCH"])
async def update_profile_me() -> tuple[Response, int]:
    data = g.data
    user_id = g.user_id
    if not data:
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with pool.acquire() as db:
        user = await users.update_user(user_id, data, db)

        if not user.success:
            return error_response(user), 400

    await cache_users.delete_user_cache(user_id)

    return response(), 204


@route(bp, "/users/<int:user_id>", methods=["GET"])
async def get_profile(user_id: int) -> tuple[Response, int]:
    user = await cache_users.get_user(user_id, pool)

    if not user.success:
        return error_response(user), 400

    assert user.data is not None
    return response(data=user.data.dict), 200


def load(app: Quart):
    app.register_blueprint(bp)
