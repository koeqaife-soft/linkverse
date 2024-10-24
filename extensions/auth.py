import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, error_response, route
from quart import g, request
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

    assert result3.data is not None

    data = {"access": result3.data["access"]}
    _response = response(data=data)

    _response.set_cookie(
        "refresh_token", result3.data["refresh"],
        httponly=True, secure=True,
        samesite='Strict',
        max_age=30*24*60*60
    )

    return _response, 201


@route(bp, '/auth/login', methods=['POST'])
async def login() -> tuple[Response, int]:
    data = g.data
    email = data.get('email')
    password = data.get('password')

    async with pool.acquire() as db:
        result = await auth.login(email, password, db)
    if not result.success:
        return error_response(result), 400

    data = {"access": result.data["access"]}
    _response = response(data=data)

    _response.set_cookie(
        "refresh_token", result.data["refresh"],
        httponly=True, secure=True,
        samesite='Strict',
        max_age=30*24*60*60
    )

    return _response, 200


@route(bp, '/auth/refresh', methods=['POST'])
async def refresh() -> tuple[Response, int]:
    data = g.data
    token = data.get("refresh_token") or request.cookies.get("refresh_token")
    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with pool.acquire() as db:
        result = await auth.refresh(token, db)
    if not result.success:
        return error_response(result), 400

    data = {"access": result.data["access"]}
    _response = response(data=data)

    _response.set_cookie(
        "refresh_token", result.data["refresh"],
        httponly=True, secure=True,
        samesite='Strict',
        max_age=30*24*60*60
    )

    return _response, 200


@route(bp, '/auth/logout', methods=['POST'])
async def logout() -> tuple[Response, int]:
    token = request.headers.get("Authorization")
    if token is None:
        return response(error=True, error_msg="UNAUTHORIZED"), 401

    async with pool.acquire() as db:
        result = await auth.check_token(token, db)

        if not result.success:
            return error_response(result), 400

        data = result.data or {}
        result2 = await auth.remove_secret(
            data["secret"], data["user_id"], db
        )

        if not result2.success:
            return error_response(result2), 500

    _response = response()
    _response.delete_cookie(
        "refresh_token", httponly=True,
        secure=True, samesite='Strict'
    )

    return _response, 204


def load(app: Quart):
    app.register_blueprint(bp)
