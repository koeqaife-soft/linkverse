import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
from utils.database import AutoConnection
import typing as t
from utils.storage import generate_signed_token, PUBLIC_PATH
from utils.storage import create_file_context  # , add_object_to_file
import os
from urllib.parse import quote

bp = Blueprint('storage', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool

LIMITS = {
    "avatar": 2,
    "banner": 8,
    "context": 10
}


def create_random_string() -> str:
    _bytes = os.urandom(32)
    return _bytes.hex()


@route(bp, "/storage/context", methods=["POST"])
async def create_context() -> tuple[Response, int]:
    # TODO: Create context
    raise NotImplementedError


@route(bp, "/storage/context/<id>", methods=["DELETE"])
async def delete_context(id: str) -> tuple[Response, int]:
    # TODO: Delete context
    raise NotImplementedError


@route(bp, "/storage/file", methods=["POST"])
async def upload_file() -> tuple[Response, int]:
    data = g.data
    _file_name = quote(data["file_name"])
    _type: t.Literal["avatar", "banner", "context"] = data["type"]
    context_id: str = data.get("context_id")

    async with AutoConnection(pool) as conn:
        if _type == "context":
            if not context_id:
                raise FunctionError("INCORRECT_DATA", 400, None)
            # TODO: Check context and increase count of uses for limiting
            raise NotImplementedError
        else:
            subfolder = "avatars" if _type == "avatar" else "banners"
            file_name = f"public/{subfolder}/{g.user_id}/{_file_name}"
            context_id = (await create_file_context(
                g.user_id, [file_name], 0, conn
            )).data
        token = generate_signed_token(
            [("GET", file_name), ("PUT", file_name)],
            expires=900,  # 15 minutes
            max_size=LIMITS[_type]
        )

    return response(data={
        "file_url": f"{PUBLIC_PATH}/{file_name}",
        "headers": {
            "X-Custom-Auth": token
        },
        "file_name": _file_name,
        "context_id": context_id
    }), 200


def load(app: Quart):
    app.register_blueprint(bp)
