from core import app, response
import asyncpg
import traceback
import uuid
from quart import request, g
import os
from utils.database import initialize_database, create_pool
import utils.auth as auth
from supabase import acreate_client
from supabase.client import ClientOptions, AsyncClient
import uvloop
import json


debug = os.getenv('DEBUG') == 'True'
supabase_url: str = os.environ.get("SUPABASE_URL")  # type: ignore
supabase_key: str = os.environ.get("SUPABASE_KEY")  # type: ignore
supabase: AsyncClient
pool: asyncpg.pool.Pool


@app.errorhandler(500)
async def handle_500(error):
    traceback.print_exc()
    return response(error=True, error_msg="INTERNAL_SERVER_ERROR"), 500


@app.before_request
async def before():
    url_rule = str(request.url_rule).lstrip("/").split("/")
    if url_rule[1] != "auth":
        headers = request.headers
        token = headers.get("Authorization")
        if token is None:
            return response(error=True, error_msg="UNAUTHORIZED"), 401
        async with pool.acquire() as db:
            result = await auth.check_token(token, db)
        if not result.success:
            error_msg = result.message or "UNAUTHORIZED"
            return response(error=True, error_msg=error_msg)

        g.user_id = result.data["user_id"]


@app.route('/v1/generate_upload_url', methods=['POST'])
async def generate_upload_url():
    data = await request.get_json()

    file_name = data.get('file_name', '')
    random_file_name = f"user/{uuid.uuid4()}.{file_name}"

    upload_url = await (
        supabase.storage.from_('default')
        .create_signed_upload_url(random_file_name)
    )

    return response(data={
        "upload_url": upload_url['signed_url'],
        "file_url": (
            f"{supabase_url}/storage/v1/object/public/default/" +
            f"{random_file_name}"
        ),
        "file_name": random_file_name
    }), 200


@app.route('/v1/auth/register', methods=['POST'])
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


@app.route('/v1/auth/login', methods=['POST'])
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


@app.route('/v1/auth/refresh', methods=['POST'])
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


@app.before_serving
async def startup():
    global supabase, pool
    with open("postgres.json") as f:
        config = json.load(f)
    pool = await create_pool(**config)
    supabase = await acreate_client(
        supabase_url, supabase_key,
        options=ClientOptions(
            storage_client_timeout=10
        )
    )
    async with pool.acquire() as db:
        await initialize_database(db)


@app.after_serving
async def shutdown():
    global pool
    await pool.close()


if __name__ == '__main__':
    uvloop.install()
    app.run(port=6169, debug=debug)
