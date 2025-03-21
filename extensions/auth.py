import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g, request
import utils.auth as auth
from utils.cache import auth as auth_cache
from utils.database import AutoConnection
from utils.realtime import RealtimeManager, SessionActions
import os

debug = os.getenv('DEBUG') == 'True'
bp = Blueprint('auth', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


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
        raise FunctionError("UNAUTHORIZED", 401, None)

    async with AutoConnection(pool) as conn:
        result = await auth.refresh(token, conn)

    decoded = result.data["decoded"]

    await rt_manager.session_event(
        decoded["user_id"], SessionActions.CHECK_TOKEN,
        decoded["session_id"]
    )

    return response(data=result.data["tokens"]), 200


@route(bp, '/auth/logout', methods=['POST'])
async def logout() -> tuple[Response, int]:
    token = request.headers.get("Authorization")

    if token is None:
        raise FunctionError("UNAUTHORIZED", 401, None)

    async with AutoConnection(pool) as conn:
        result = await auth.check_token(token, conn)

        data = result.data
        await auth.remove_secret(
            data["secret"], data["user_id"], conn
        )
        await auth_cache.clear_token_cache(data)
        await rt_manager.session_event(
            result.data["user_id"], SessionActions.SESSION_LOGOUT,
            result.data["session_id"]
        )

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
