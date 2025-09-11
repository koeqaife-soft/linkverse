import hashlib
import hmac
import base64
import time
import orjson
import os
import typing as t
from utils.database import AutoConnection
from core import Status, FunctionError, Global
from utils.generation import generate_id
import aiohttp
import logging

logger = logging.getLogger("linkverse.storage")

gb = Global()
pool = gb.pool

PUBLIC_PATH = "https://storage.sharinflame.com"
SECRET_KEY = os.environ["CDN_SECRET_KEY"].encode()
SECRET_KEY_N = os.environ["CDN_SECRET_KEY_N"]
type Operation = t.Literal[
    "PUT", "DELETE", "GET", "HEAD"
]


def sign(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def generate_signed_token(
    allowed_operations: list[tuple[Operation, str]],
    expires: int,
    max_size: int | None = None,
    type: str | None = None
) -> dict[str, str]:
    """Create presigned url for Cloudflare R2 Worker

    Args:
        allowed_operations (list[tuple[Operation, str]]):
            e.g. "PUT", "path/to/object"
        expires (int): Time in seconds (not timestamp)
        max_size (int): Size in mb

    Returns:
        str: Token to give to Worker
    """
    expires_timestamp = time.time() + expires

    operations = []
    for _tuple in allowed_operations:
        operation = _tuple[0].upper()
        path = _tuple[1].lstrip("/")
        operations.append(f"{operation}:{path}")

    payload = {
        "expires": expires_timestamp,
        "allowed_operations": operations
    }
    if max_size is not None:
        payload["max_size"] = max_size
    if type is not None:
        payload["type"] = type
    payload_b64 = base64.b64encode(orjson.dumps(payload))
    signature = base64.b64encode(sign(SECRET_KEY, payload_b64))
    return f"LV {SECRET_KEY_N}.{payload_b64.decode()}.{signature.decode()}"


def build_get_link(
    object: str,
    expires: int = 259200  # 3 days
) -> str:
    full_path = f"{PUBLIC_PATH}/{object}"

    if object.startswith("public/"):
        return full_path

    expires_timestamp = int(time.time() + expires)

    payload = str(expires_timestamp)
    payload_b64 = (
        base64.urlsafe_b64encode(payload.encode())
        .decode()
        .rstrip("=")
    )
    signature_payload = f"{object}|{expires_timestamp}".encode()
    signature = (
        base64.urlsafe_b64encode(sign(SECRET_KEY, signature_payload))
        .decode()
        .rstrip("=")
    )
    token = f"lv.{SECRET_KEY_N}.{payload_b64}.{signature}"
    full_path += f"?token={token}"
    return full_path


async def create_file_context(
    user_id: int,
    objects: list[str],
    max_count: int,
    type: str,
    conn: AutoConnection
) -> Status[str]:
    db = await conn.create_conn()
    new_id = str(generate_id())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO files
            (user_id, objects, allowed_count, context_id, type)
            VALUES ($1, $2, $3, $4, $5)
            """, user_id, objects, max_count, new_id, type
        )

    return Status(True, data=new_id)


async def delete_file_context(
    context_id: int, conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()

    async with db.transaction():
        await db.execute(
            """
            DELETE FROM files
            WHERE context_id = $1
            """, context_id
        )


async def check_allowed_count(
    context_id: str, conn: AutoConnection
) -> Status[int]:
    db = await conn.create_conn()

    row = await db.fetchrow(
        """
        SELECT allowed_count
        FROM files
        WHERE context_id = $1
        """,
        context_id
    )

    if not row:
        raise FunctionError("CONTEXT_NOT_FOUND", 404, None)

    return Status(True, data=row["allowed_count"])


async def add_object_to_file(
    context_id: str,
    new_object: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()

    async with db.transaction():
        row = await db.fetchrow(
            """
            SELECT objects, allowed_count
            FROM files
            WHERE context_id = $1
            FOR UPDATE
            """,
            context_id
        )

        if not row:
            raise FunctionError("CONTEXT_NOT_FOUND", 404, None)

        if row["allowed_count"] <= 0:
            raise FunctionError("MAX_COUNT_EXCEED", 403, None)

        objects = row["objects"] + [new_object]
        allowed_count = row["allowed_count"] - 1

        await db.execute(
            """
            UPDATE files
            SET objects = $1,
                allowed_count = $2
            WHERE context_id = $3
            """,
            objects, allowed_count, context_id
        )

    return Status(True)


async def get_context(
    context_id: int, conn: AutoConnection
) -> Status[dict]:
    db = await conn.create_conn()
    row = await db.fetchrow(
        """
        SELECT objects, user_id, created_at, type
        FROM files
        WHERE context_id = $1
        """,
        context_id
    )

    if not row:
        raise FunctionError("CONTEXT_NOT_FOUND", 404, None)

    return Status(True, data={
        "user_id": row["user_id"],
        "objects": row["objects"],
        "created_at": int(row["created_at"].timestamp()),
        "type": row["type"]
    })


async def delete_object(
    object_path: str,
    session: aiohttp.ClientSession
) -> None:
    token = generate_signed_token([("DELETE", object_path)], 60)
    async with session.delete(
        f"{PUBLIC_PATH}/{object_path}",
        headers={
            "X-Custom-Auth": token
        }
    ) as request:
        if request.status == 404:
            return
        request.raise_for_status()
