import hashlib
import hmac
import base64
import time
import orjson
import os
import typing as t


SECRET_KEY = os.environ["CDN_SECRET_KEY"].encode()
SECRET_KEY_N = os.environ["CDN_SECRET_KEY_N"]
type Operation = t.Literal[
    "PUT", "DELETE", "GET"
]


def sign(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def generate_signed_token(
    allowed_operations: list[tuple[Operation, str]],
    expires: int,
    max_size: int
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
        "allowed_operations": operations,
        "max_size": max_size
    }
    payload_b64 = base64.b64encode(orjson.dumps(payload))
    signature = base64.b64encode(sign(SECRET_KEY, payload_b64))
    return f"LV {SECRET_KEY_N}.{payload_b64.decode()}.{signature.decode()}"
