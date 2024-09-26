import asyncpg
from quart import Blueprint, Quart
from core import response, Global
from quart import request
import utils.auth as auth

bp = Blueprint('auth', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@bp.route('/v1/auth/register', methods=['POST'])
async def auth_register():
    data = await request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if username is None or email is None or password is None:
        return response(error=True, error_msg="MISSING_DATA"), 400

    async with pool.acquire() as db:
        result = await auth.check_username(username, db)
        if not result.success:
            return response(error=True, error_msg=result.message), 400

        result = await auth.create_user(username, email, password, db)
        if not result.success:
            return response(error=True, error_msg=result.message), 400

        result = await auth.create_token(result.data, db)
        if not result.success:
            return response(error=True, error_msg=result.message), 500

    return response(data=result.data), 200


@bp.route('/v1/auth/login', methods=['POST'])
async def auth_login():
    data = await request.get_json()
    email = data.get('email')
    password = data.get('password')

    if email is None or password is None:
        return response(error=True, error_msg="MISSING_DATA"), 400

    async with pool.acquire() as db:
        result = await auth.login(email, password, db)
    if not result.success:
        return response(error=True, error_msg=result.message), 400

    return response(data=result.data), 200


@bp.route('/v1/auth/refresh', methods=['POST'])
async def auth_refresh():
    data = await request.get_json()
    token = data.get('refresh_token')

    if token is None:
        return response(error=True, error_msg="MISSING_DATA"), 400

    async with pool.acquire() as db:
        result = await auth.refresh(token, db)
    if not result.success:
        return response(error=True, error_msg=result.message), 400

    return response(data=result.data), 200


def load(app: Quart):
    app.register_blueprint(bp)
