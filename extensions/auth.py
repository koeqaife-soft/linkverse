import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, error_response, route
from quart import g
import utils.auth as auth

bp = Blueprint('auth', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, '/auth/register', methods=['POST'])
async def register() -> tuple[Response, int]:
    data = g.data
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    async with pool.acquire() as db:
        result = await auth.check_username(username, db)
        if not result.success:
            return error_response(result), 400

        result2 = await auth.create_user(username, email, password, db)
        if not result2.success:
            return error_response(result2), 400

        result3 = await auth.create_token(result2.data, db)  # type: ignore
        if not result3.success:
            return error_response(result3), 500

    return response(data=result3.data or {}), 201


@route(bp, '/auth/login', methods=['POST'])
async def login() -> tuple[Response, int]:
    data = g.data
    email = data.get('email')
    password = data.get('password')

    async with pool.acquire() as db:
        result = await auth.login(email, password, db)
    if not result.success:
        return error_response(result), 400

    return response(data=result.data), 200


@route(bp, '/auth/refresh', methods=['POST'])
async def refresh() -> tuple[Response, int]:
    data = g.data
    token = data.get('refresh_token')

    async with pool.acquire() as db:
        result = await auth.refresh(token, db)
    if not result.success:
        return error_response(result), 400

    return response(data=result.data), 200


def load(app: Quart):
    app.register_blueprint(bp)
