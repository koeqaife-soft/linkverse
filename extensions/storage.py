import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
# from utils.database import AutoConnection
import typing as t
from utils.storage import generate_signed_token
import os
from urllib.parse import quote

bp = Blueprint('storage', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool

PUBLIC_PATH = "https://storage.sharinflame.com"
PUBLIC_BUCKET_NAME = "linkverse"


def create_random_string() -> str:
    _bytes = os.urandom(32)
    return _bytes.hex()


@route(bp, "/storage/context", methods=["POST"])
async def create_context() -> tuple[Response, int]:
    # TODO: Create context
    raise NotImplementedError


@route(bp, "/storage/context", methods=["DELETE"])
async def delete_context() -> tuple[Response, int]:
    # TODO: Delete context
    raise NotImplementedError


@route(bp, "/storage/file", methods=["POST"])
async def upload_file() -> tuple[Response, int]:
    data = g.data
    _file_name = data["file_name"]
    _type: t.Literal["avatar", "banner", "context"] = data["type"]
    context_id = data.get("context_id")

    if _type == "context":
        if not context_id:
            raise FunctionError("INCORRECT_DATA", 400, None)
        # TODO: Check context and increase count of uses for limiting
        raise NotImplementedError

    file_name = quote(
        f"{create_random_string()}/{_file_name}",
        safe="/"
    )
    token = generate_signed_token(
        [("GET", file_name), ("PUT", file_name)],
        expires=900,  # 15 minutes
        max_size=10
    )

    return response(data={
        "file_url": f"{PUBLIC_PATH}/{file_name}",
        "headers": {
            "X-Custom-Auth": token
        },
        "file_name": file_name
    }), 200


def load(app: Quart):
    app.register_blueprint(bp)
