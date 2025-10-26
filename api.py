import asyncpg
import quart
from extensions import load_all
from core import app, response, route, setup_logger, Global, FunctionError
from core import get_proc_identity, compress
from core import compress_config, flatten_dict
import traceback
from quart import request, g, websocket
import os
import aiofiles
from datetime import datetime, timezone
import asyncio
import werkzeug.exceptions
import core
import json5
import utils.cache as cache
from utils.database import AutoConnection, create_pool
from utils.cache import auth as cache_auth
from redis.asyncio import Redis
from queues.scheduler import start_scheduler
from realtime.websocket import bp as ws_bp

debug = os.getenv('DEBUG') == 'True'
gb = Global()

pool: asyncpg.Pool = gb.pool
redis: Redis = gb.redis

logger = setup_logger()
with open("config/endpoints.json5", 'r') as f:
    endpoints_data: dict = json5.load(f)
    endpoints_data = flatten_dict(endpoints_data)


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

    if quart.has_request_context():
        error_message = (
            "---\n" +
            f"Internal Server Error ({current_time})\n" +
            f"Endpoint: {request.endpoint}, URL Rule: {request.url_rule}\n" +
            f"IP: {request.remote_addr}\n"
            f"{tb_str}" +
            "---\n\n"
        )
        file_name = f"error_{request.endpoint}.log"
    elif quart.has_websocket_context():
        error_message = (
            "---\n" +
            f"Internal Server Error ({current_time})\n" +
            f"Endpoint: {websocket.endpoint} (WebSocket!)\n" +
            f"IP: {websocket.remote_addr}\n"
            f"{tb_str}" +
            "---\n\n"
        )
        file_name = "error_websocket.log"
    else:
        error_message = (
            "---\n" +
            f"Internal Server Error ({current_time})\n" +
            f"{tb_str}" +
            "---\n\n"
        )
        file_name = "error_app.log"

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
            data[key], value,
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

    _data = endpoints_data.get(request.endpoint, {})
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

        g.user_id = result["user_id"]
        g.session_id = result["session_id"]


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


@app.before_serving
async def startup():
    with open("config/postgres.json") as f:
        config = json5.load(f)
    pool = await create_pool(**config)
    gb.pool = pool

    redis_host = os.environ["REDIS_HOST"]
    redis_port = os.environ["REDIS_PORT"]
    url = f"redis://{redis_host}:{redis_port}"
    await cache.Cache(url).init()
    redis = Redis(host=redis_host, port=redis_port)
    gb.redis = redis

    start_scheduler()

    logger.info("Worker started!")


@app.after_serving
async def shutdown():
    global pool
    await pool.close()

    worker_id = get_proc_identity()
    if worker_id != 0:
        logger.warning("Stopping worker")


load_all(app)
app.register_blueprint(ws_bp)


if __name__ == '__main__':
    app.run(port=6169, debug=debug, host="0.0.0.0",
            keyfile=os.getenv("KEY_FILE"),
            certfile=os.getenv("CERT_FILE"))
