import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route
from quart import g, request
import utils.auth as auth
from utils.database import AutoConnection
import os

debug = os.getenv('DEBUG') == 'True'
bp = Blueprint('auth', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool

secure_cookie_kwargs = {
    "secure": not debug,
    "samesite": "Strict" if debug else "None"
}


def _set_token(refresh: str, access: str, response: Response):
    response.set_cookie(
        "refresh_token", refresh,
        httponly=True,
        max_age=30*24*60*60,
        **secure_cookie_kwargs
    )

    response.set_cookie(
        "access_token", access,
        httponly=True,
        max_age=30*24*60*60,
        **secure_cookie_kwargs
    )
    return response


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

    _response = response()
    _set_token(result3.data["refresh"], result3.data['access'], _response)

    return _response, 201


@route(bp, '/auth/login', methods=['POST'])
async def login() -> tuple[Response, int]:
    data = g.data
    email = data.get('email')
    password = data.get('password')

    async with AutoConnection(pool) as conn:
        result = await auth.login(email, password, conn)

    _response = response()
    _set_token(result.data["refresh"], result.data['access'], _response)

    return _response, 200


@route(bp, '/auth/refresh', methods=['POST'])
async def refresh() -> tuple[Response, int]:
    data = g.data
    token = data.get("refresh_token") or request.cookies.get("refresh_token")
    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with AutoConnection(pool) as conn:
        result = await auth.refresh(token, conn)

    _response = response()
    _set_token(result.data["refresh"], result.data['access'], _response)

    return _response, 200


@route(bp, '/auth/logout', methods=['POST'])
async def logout() -> tuple[Response, int]:
    token = (
        request.headers.get("Authorization")
        or request.cookies.get("access_token")
    )
    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with AutoConnection(pool) as conn:
        result = await auth.check_token(token, conn)

        data = result.data or {}
        await auth.remove_secret(
            data["secret"], data["user_id"], conn
        )

    _response = response()
    _response.delete_cookie(
        "refresh_token", httponly=True,
        **secure_cookie_kwargs
    )
    _response.delete_cookie(
        "access_token", httponly=True,
        **secure_cookie_kwargs
    )

    return _response, 204


@route(bp, '/auth/remove_cookies', methods=['POST'])
async def remove_cookies() -> tuple[Response, int]:
    _response = response()
    _response.delete_cookie(
        "refresh_token", httponly=True,
        **secure_cookie_kwargs
    )
    _response.delete_cookie(
        "access_token", httponly=True,
        **secure_cookie_kwargs
    )

    return _response, 204


def load(app: Quart):
    app.register_blueprint(bp)
