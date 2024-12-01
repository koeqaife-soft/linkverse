import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route
from quart import g, request
import utils.auth as auth
from utils.cache import auth as auth_cache
from utils.database import AutoConnection
import os

debug = os.getenv('DEBUG') == 'True'
bp = Blueprint('auth', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, '/auth/register', methods=['POST'])
async def register() -> tuple[Response, int]:
    data = g.data
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    async with AutoConnection(pool) as conn:
        await auth.check_username(username, conn)

        result2 = await auth.create_user(username, email, password, conn)
        result3 = await auth.create_token(result2.data, conn)

    return response(data=result3.data), 201


@route(bp, '/auth/login', methods=['POST'])
async def login() -> tuple[Response, int]:
    data = g.data
    email = data.get('email')
    password = data.get('password')

    async with AutoConnection(pool) as conn:
        result = await auth.login(email, password, conn)

    return response(data=result.data), 200


@route(bp, '/auth/refresh', methods=['POST'])
async def refresh() -> tuple[Response, int]:
    data = g.data
    token = data.get("refresh_token")
    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with AutoConnection(pool) as conn:
        result = await auth.refresh(token, conn)

    return response(data=result.data), 200


@route(bp, '/auth/logout', methods=['POST'])
async def logout() -> tuple[Response, int]:
    token = request.headers.get("Authorization")

    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with AutoConnection(pool) as conn:
        result = await auth.check_token(token, conn)

        data = result.data
        await auth.remove_secret(
            data["secret"], data["user_id"], conn
        )
        await auth_cache.clear_token_cache(token)

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
