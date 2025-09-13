import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
from utils.database import AutoConnection
from utils.storage import generate_signed_token, PUBLIC_PATH
from utils.storage import create_file_context, add_object_to_file
from utils.storage import get_context
import os
from urllib.parse import quote
import time

bp = Blueprint('storage', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool

LIMITS = {
    "avatar": 2,
    "banner": 8,
    "post_video": 15,
    "post_image": 10
}

MAX_COUNT = {
    "post_video": 1,
    "post_image": 5
}


def create_random_string() -> str:
    _bytes = os.urandom(32)
    return _bytes.hex()


@route(bp, "/storage/context", methods=["POST"])
async def create_context() -> tuple[Response, int]:
    data: dict = g.data
    type: str = data["type"]

    async with AutoConnection(pool) as conn:
        context_id = (await create_file_context(
            g.user_id, [], 5, type, conn
        )).data
    return response(data={
        "context_id": context_id,
        "max_size": LIMITS[type],
        "max_count": MAX_COUNT[type],
        "expires": time.time() + 30 * 60
    }), 200


@route(bp, "/storage/file", methods=["POST"])
async def upload_file() -> tuple[Response, int]:
    data = g.data
    _file_name = quote(data["file_name"])
    _type: str = data["type"]
    context_id: str = data.get("context_id")

    async with AutoConnection(pool) as conn:
        if _type == "context":
            if not context_id:
                raise FunctionError("INCORRECT_DATA", 400, None)

            context = (await get_context(context_id, conn)).data
            if (
                context["user_id"] != g.user_id
                or time.time() - 60 * 60 > context["created_at"]
            ):
                raise FunctionError("FORBIDDEN", 403, None)

            _type = context["type"]
            file_name = f"private/{context_id}/{_file_name}"
            await add_object_to_file(context_id, file_name, conn)
        else:
            subfolder = "avatars" if _type == "avatar" else "banners"
            context_id = (await create_file_context(
                g.user_id, [], 1, _type, conn
            )).data
            file_name = f"public/{subfolder}/{g.user_id}/{context_id}.webp"
            await add_object_to_file(context_id, file_name, conn)

        token = generate_signed_token(
            [("GET", file_name), ("PUT", file_name)],
            expires=900,  # 15 minutes
            max_size=LIMITS[_type],
            type=_type
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
