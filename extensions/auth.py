import time
import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g, request
import utils.auth as auth
from utils.cache import auth as auth_cache
from utils.database import AutoConnection
from utils.rate_limiting import ip_rate_limit, rate_limit
from utils.email import create_token, new_code, verify_token
from utils.email import templates, send_email, TokenType
from realtime.broker import publish_event
import os

debug = os.getenv('DEBUG') == 'True'
bp = Blueprint('auth', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool


@route(bp, '/auth/check', methods=['GET'])
@ip_rate_limit(30, 60)
async def check() -> tuple[Response, int]:
    params = g.params
    value = params.get('value')
    type = params.get('type')
    async with AutoConnection(pool) as conn:
        if type == 'email':
            await auth.check_email(value, conn)
        elif type == 'username':
            await auth.check_username(value, conn)

    return response(is_empty=True), 204


@route(bp, '/auth/register', methods=['POST'])
@ip_rate_limit(20, 24 * 60 * 60)
@ip_rate_limit(2, 60)
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

    await publish_event(
        f"session:{decoded["session_id"]}",
        {"type": "check_token"}
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

    await publish_event(
        f"session:{data["session_id"]}",
        {"type": "session_logout"}
    )

    return response(), 204


@route(bp, "/auth/me", methods=["GET"])
@rate_limit(45, 60)
async def get_auth_me() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await auth.get_user(g.user_id, conn)
        user_dict = user.data.dict
        del user_dict["password_hash"]

    return response(data=user_dict, cache=True), 200


@route(bp, "/auth/email/verify/send", methods=["POST"])
@rate_limit(5, 24 * 60 * 60)
@rate_limit(1, 60)
async def send_verification() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = (
            await auth.get_user(g.user_id, conn)
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
            await auth.get_user(g.user_id, conn)
        ).data
        if user.email != email:
            raise FunctionError("EMAIL_HAS_CHANGED", 400, None)
        await auth.set_email_verified(g.user_id, True, conn)

    return response(is_empty=True), 204


@route(bp, "/auth/change_password", methods=["POST"])
@rate_limit(10, 60 * 60)
async def change_password() -> tuple[Response, int]:
    data = g.data
    old_password: str = data["old_password"]
    new_password: str = data["new_password"]
    close_sessions: bool = data["close_sessions"]

    async with AutoConnection(pool) as conn:
        user = (
            await auth.get_user(g.user_id, conn)
        ).data
        if not (await auth.check_password(user.password_hash, old_password)):
            raise FunctionError("INCORRECT_PASSWORD", 400, None)

        await auth.update_password(user.user_id, new_password, conn)
        if close_sessions:
            await auth.close_sessions_except(g.user_id, g.session_id, conn)

    await publish_event(
        f"session:{g.user_id}",
        {"type": "check_token"}
    )

    await auth_cache.clear_all_tokens(g.user_id)

    return response(is_empty=True), 204


@route(bp, "/auth/change_email/send", methods=["POST"])
@rate_limit(5, 24 * 60 * 60)
@rate_limit(2, 60)
async def change_email_send() -> tuple[Response, int]:
    data = g.data
    password: str = data["password"]
    new_email: str = data["new_email"].strip()

    async with AutoConnection(pool) as conn:
        await auth.check_email(new_email, conn)

        user = (
            await auth.get_user(g.user_id, conn)
        ).data
        if user.email == new_email:
            raise FunctionError("INCORRECT_DATA", 400, None)
        if not (await auth.check_password(user.password_hash, password)):
            raise FunctionError("INCORRECT_PASSWORD", 400, None)

    code = new_code()
    token = create_token(code, new_email, TokenType.NEW_EMAIL)
    await send_email(
        new_email,
        templates["email_verification"]["en-US"],
        {"name": user.username, "code": code}
    )

    return response(data={
        "token": token
    }), 200


def calc_pending_until(user_created_at: int) -> float:
    now = time.time()
    account_age = now - user_created_at

    min_seconds = 1 * 60 * 60
    max_seconds = 5 * 24 * 60 * 60
    max_age = 365 * 24 * 60 * 60

    factor = min(account_age / max_age, 1.0)

    extra_time = min_seconds + (max_seconds - min_seconds) * factor
    return now + extra_time


@route(bp, "/auth/change_email/check", methods=["POST"])
@rate_limit(5, 60)
async def change_email_check() -> tuple[Response, int]:
    data = g.data
    code: str = data["code"]
    token: str = data["token"]
    email_or_error, success = verify_token(code, token, TokenType.NEW_EMAIL)

    if success:
        email = email_or_error
    else:
        error = email_or_error
        raise FunctionError(error, 400, None)

    pending_until: int | None = None
    async with AutoConnection(pool) as conn:
        user = (
            await auth.get_user(g.user_id, conn)
        ).data
        if user.email_verified:
            pending_until = calc_pending_until(user.created_at)
            await auth.set_pending(
                g.user_id,
                email,
                pending_until,
                conn
            )
        else:
            await auth.set_email(g.user_id, email, conn)
            await auth.set_email_verified(g.user_id, True, conn)

    return response(data={
        "pending_until": pending_until
    }), 200


@route(bp, "/auth/change_email/cancel", methods=["POST"])
@rate_limit(5, 60)
async def change_email_cancel() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await auth.set_pending(
            g.user_id,
            None,
            None,
            conn
        )

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
