import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g, request
import utils.auth as auth
from utils.cache import auth as auth_cache
from utils.database import AutoConnection
from utils.realtime import RealtimeManager, SessionActions
from utils.rate_limiting import ip_rate_limit, rate_limit
from utils.email import create_token, new_code, verify_token
from utils.email import templates, send_email
import os

debug = os.getenv('DEBUG') == 'True'
bp = Blueprint('auth', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


@route(bp, '/auth/register', methods=['POST'])
@ip_rate_limit(20, 24 * 60 * 60)
@ip_rate_limit(5, 60)
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
@ip_rate_limit(30, 24 * 60 * 60)
@ip_rate_limit(5, 60)
async def login() -> tuple[Response, int]:
    data = g.data
    email = data.get('email')
    password = data.get('password')

    async with AutoConnection(pool) as conn:
        result = await auth.login(email, password, conn)

    return response(data=result.data), 200


@route(bp, '/auth/refresh', methods=['POST'])
@ip_rate_limit(30, 24 * 60 * 60)
@ip_rate_limit(5, 60)
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
@ip_rate_limit(20, 60)
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


@route(bp, "/auth/me", methods=["GET"])
@rate_limit(45, 60)
async def get_auth_me() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await auth.get_user({"user_id": g.user_id}, conn)
        user_dict = user.data.dict
        del user_dict["password_hash"]

    return response(data=user_dict, cache=True), 200


@route(bp, "/auth/email/verify/send", methods=["POST"])
@rate_limit(5, 24 * 60 * 60)
@rate_limit(1, 60)
async def send_verification() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = (
            await auth.get_user({"user_id": g.user_id}, conn)
        ).data

    if user.email_verified:
        raise FunctionError("ALREADY_VERIFIED", 400, None)

    code = new_code()
    token = create_token(code, user.email)
    await send_email(
        user.email,
        templates["email_verification"]["en-US"],
        {"name": user.username, "code": code}
    )

    return response(data={
        "token": token
    }), 200


@route(bp, "/auth/email/verify/check", methods=["POST"])
@rate_limit(5, 60)
async def check_verification() -> tuple[Response, int]:
    data = g.data
    code: str = data["code"]
    token: str = data["token"]
    email_or_error, success = verify_token(code, token)

    if success:
        email = email_or_error
    else:
        error = email_or_error
        raise FunctionError(error, 400, None)

    async with AutoConnection(pool) as conn:
        user = (
            await auth.get_user({"user_id": g.user_id}, conn)
        ).data
        if user.email != email:
            raise FunctionError("EMAIL_HAS_CHANGED", 400, None)
        await auth.set_email_verified(g.user_id, True, conn)

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
