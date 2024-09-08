import asyncio
import logging
import traceback
import uuid
from quart import request
import os
from utils.generation import generate_id, Action
from utils.database import initialize_database
import utils.auth as auth
from supabase import acreate_client
from supabase.client import ClientOptions, AsyncClient
from core import app, response
import core
import aiosqlite


SESSION_ID = generate_id(Action.SESSION)

debug = os.getenv('DEBUG') == 'True'
supabase_url: str = os.environ.get("SUPABASE_URL")  # type: ignore
supabase_key: str = os.environ.get("SUPABASE_KEY")  # type: ignore
supabase: AsyncClient
db: aiosqlite.Connection


@app.errorhandler(500)
async def handle_500(error):
    traceback.print_exc()
    return response(error=True, error_msg="INTERNAL_SERVER_ERROR"), 500


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
    result = await auth.create_user(username, email, password, db)
    if not result.success:
        return response(error=True, error_msg=result.message), 400

    result = await auth.login(email, password, db)
    if result.success:
        return response(error=True, error_msg=result.message), 500

    return response(data=result.data), 200


@app.route('/v1/auth/login', methods=['POST'])
async def auth_login():
    ...


async def main_task():
    global supabase, db
    async with aiosqlite.connect("./database/main.db") as db:
        supabase = await acreate_client(
            supabase_url, supabase_key,
            options=ClientOptions(
                storage_client_timeout=10
            )
        )
        await initialize_database(db)

        quart_task = asyncio.create_task(
            app.run_task(
                debug=debug, port=6169,
                # certfile="cert.pem",
                # keyfile="key.pem"
            )
        )
        await asyncio.gather(quart_task)


if __name__ == '__main__':
    asyncio.run(main_task())
