import asyncpg
from core import app, response, setup_logger, Global
from core import worker_count, get_proc_identity, load_extensions
import traceback
import uuid
from quart import request, g
import os
from utils.database import create_pool
import utils.auth as auth
from supabase import acreate_client
from supabase.client import ClientOptions, AsyncClient
import aiofiles
from datetime import datetime, timezone
import asyncio
import json
import werkzeug.exceptions
import core
import json5
import utils.cache as cache

debug = os.getenv('DEBUG') == 'True'
supabase_url: str = os.environ.get("SUPABASE_URL")  # type: ignore
supabase_key: str = os.environ.get("SUPABASE_KEY")  # type: ignore
supabase: AsyncClient
_g = Global()
pool: asyncpg.Pool = _g.pool
logger = setup_logger()
with open("config/endpoints.json5", 'r') as f:
    endpoints_data: dict = json5.load(f)


async def log_error_to_file(message: str, file: str):
    os.makedirs("logs", exist_ok=True)
    async with aiofiles.open(f"logs/{file}", mode="a") as f:
        await f.write(message)


@app.errorhandler(500)
async def handle_500(error: werkzeug.exceptions.InternalServerError):
    current_time = (
        datetime.now(timezone.utc)
        .strftime('%Y-%m-%d %H:%M:%S')
    )

    e = error.original_exception or error
    tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))

    error_message = (
        "---\n" +
        f"Internal Server Error ({current_time})\n" +
        f"Endpoint: {request.endpoint}, URL Rule: {request.url_rule}\n" +
        f"IP: {request.remote_addr}\n"
        f"{tb_str}" +
        "---\n\n"
    )
    file_name = f"error_{request.endpoint}.log"
    asyncio.create_task(log_error_to_file(error_message, file_name))
    return response(error=True, error_msg="INTERNAL_SERVER_ERROR"), 500


@app.before_request
async def before():
    if request.endpoint is None:
        return
    data_error = (response(error=True, error_msg="INCORRECT_DATA"), 400)
    _data = core.get_value_from_dict(endpoints_data, request.endpoint)

    if _data.get("load_data"):
        data = (await request.get_json()) or {}
        g.data = data
        if "data" in _data:
            keys_present = (
                data and core.are_all_keys_present(_data["data"], data)
            )
            if not keys_present:
                return data_error

            valid_data = all(
                core.validate(data[key], core.get_options(value))
                for key, value in _data["data"].items()
                if key in data
            )
            if not valid_data:
                return data_error

        if "optional_data" in _data:
            for key, value in data.items():
                if key in _data["optional_data"]:
                    options = core.get_options(_data["optional_data"][key])
                    if not core.validate(value, options):
                        return data_error

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
            return response(error=True, error_msg=error_msg), 401

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


@app.before_serving
async def startup():
    global supabase

    worker_id = get_proc_identity()

    with open("postgres.json") as f:
        config = json.load(f)
    pool = await create_pool(**config)
    _g.pool = pool
    supabase = await acreate_client(
        supabase_url, supabase_key,
        options=ClientOptions(
            storage_client_timeout=10
        )
    )

    with open("redis.json") as f:
        redis = json.load(f)
    await cache.Cache(redis["url"]).init()

    logger.info(
        "Worker started!" +
        (f" ({worker_id}/{worker_count})" if worker_id != 0 else "")
    )


@app.after_serving
async def shutdown():
    global pool
    await pool.close()

    worker_id = get_proc_identity()
    if worker_id != 0:
        logger.warning(
            "Stopping worker" +
            (f" ({worker_id}/{worker_count})" if worker_id != 0 else "")
        )


load_extensions(debug=debug)

if __name__ == '__main__':
    app.run(port=6169, debug=debug)
