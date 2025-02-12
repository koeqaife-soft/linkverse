import asyncpg
import quart
from core import app, response, route, setup_logger, Global, FunctionError
from core import worker_count, get_proc_identity, load_extensions, compress
from core import compress_config
import traceback
import uuid
from quart import request, g
import os
from utils.database import create_pool
from supabase import acreate_client
from supabase.client import ClientOptions, AsyncClient
import aiofiles
from datetime import datetime, timezone
import asyncio
import ujson  # type: ignore
import werkzeug.exceptions
import core
import json5
import utils.cache as cache
from utils.database import AutoConnection
from utils.cache import auth as cache_auth

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


@app.errorhandler(FunctionError)
async def handle_error(error: FunctionError):
    return error.response()


@app.errorhandler(500)
async def handle_500(error: werkzeug.exceptions.InternalServerError):
    e = error.original_exception or error

    current_time = (
        datetime.now(timezone.utc)
        .strftime('%Y-%m-%d %H:%M:%S')
    )

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


def validate_data(
    _data: dict, params: bool, validate: dict,
    optional: bool
) -> tuple[bool, dict | None]:
    data = dict(_data)
    keys_present = (
        optional or (data and core.are_all_keys_present(validate, data))
    )
    if not keys_present:
        return False, None

    for key, value in validate.items():
        if key not in data:
            continue
        valid, modified = core.validate(
            data[key], core.get_options(value),
            params
        )
        if not valid:
            return False, None
        data[key] = modified

    return True, data


@app.before_request
async def before():
    if request.method == 'OPTIONS':
        return '', 204
    if request.endpoint is None:
        return

    _data = core.get_value_from_dict(endpoints_data, request.endpoint)
    if _data.get("skip_checks", False):
        return

    params = dict(request.args)

    data_error = (response(error=True, error_msg="INCORRECT_DATA"), 400)
    params_error = (response(error=True, error_msg="INCORRECT_PARAMS"), 400)

    if _data.get("load_data"):
        data = await request.get_json() or {}
        if "data" in _data:
            valid, modified = validate_data(
                data, False, _data["data"], False
            )
            if not valid:
                return data_error
            data = modified

        if "optional_data" in _data:
            valid, modified = validate_data(
                data, False, _data["optional_data"], True
            )
            if not valid:
                return data_error
            data = modified

        g.data = data

    if _data.get("params"):
        valid, modified = validate_data(
            params, True, _data["params"], False
        )
        if not valid:
            return params_error
        params = modified

    if _data.get("optional_params"):
        valid, modified = validate_data(
            params, True, _data["optional_params"], True
        )
        if not valid:
            return params_error
        params = modified

    g.params = params

    if not _data.get("no_auth", False):
        headers = request.headers
        token = headers.get("Authorization")
        if token is None:
            return response(error=True, error_msg="UNAUTHORIZED"), 401
        async with AutoConnection(pool) as conn:
            result = await cache_auth.check_token(token, conn)
        if not result.success:
            error_msg = result.message or "UNAUTHORIZED"
            return response(error=True, error_msg=error_msg), 401

        g.user_id = result.data["user_id"]


compress_conditions = [
    lambda r: not (200 <= r.status_code < 300 and
                   r.status_code != 204),
    lambda r: r.mimetype not in compress_config["mimetypes"],  # type: ignore
    lambda r: "Content-Encoding" in r.headers,
    lambda r: not r.content_length,
    lambda r: r.content_length < compress_config["min_size"]
]


@app.after_request
async def after(response: quart.Response):
    if response.status_code == 204:
        response.headers.clear()
        return response

    response = await check_cache(response)
    response = await compress_response(response)
    return response


async def check_cache(response: quart.Response):
    if request.method != 'GET':
        return response
    if request.endpoint is None:
        return response

    etag = response.get_etag()

    if request.headers.get('If-None-Match', "").strip('"') == etag[0]:
        response.status_code = 304
        response.set_data(b'')
        response.headers.clear()
        return response

    return response


async def compress_response(response: quart.Response):
    for check in compress_conditions:
        if check(response):
            return response

    accept_encoding = request.headers.get("Accept-Encoding", "").lower()
    if not accept_encoding:
        return response

    if "br" in accept_encoding:
        algorithm = "br"
    elif "gzip" in accept_encoding:
        algorithm = "gzip"
    else:
        return response

    data = await response.get_data()

    compressed_content = await compress(data, algorithm)

    response.set_data(compressed_content)

    response.headers["Content-Encoding"] = algorithm
    response.headers["Content-Length"] = response.content_length

    vary = response.headers.get("Vary")
    if vary:
        if "accept-encoding" not in vary.lower():
            response.headers["Vary"] = f"{vary}, Accept-Encoding"
    else:
        response.headers["Vary"] = "Accept-Encoding"

    return response


@route(app, "/ping", methods=['POST', 'GET'])
async def ping():
    return response(is_empty=True), 204


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

    with open("config/postgres.json") as f:
        config = ujson.load(f)
    pool = await create_pool(**config)
    _g.pool = pool
    supabase = await acreate_client(
        supabase_url, supabase_key,
        options=ClientOptions(
            storage_client_timeout=10
        )
    )

    redis_host = os.environ["REDIS_HOST"]
    redis_port = os.environ["REDIS_PORT"]
    url = f"redis://{redis_host}:{redis_port}"
    await cache.Cache(url).init()

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
    app.run(port=6169, debug=debug, host="0.0.0.0")
