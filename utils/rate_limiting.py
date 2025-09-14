import asyncio
import time
import uuid
from functools import wraps
from typing import Any, Awaitable, Callable

from core import Global, response
from quart import g, request
from redis.asyncio import Redis

gb: Global = Global()
redis: Redis = gb.redis

with open("redis/rate_limit.lua") as f:
    _LUA_SCRIPT = f.read()

_lua_sha: str | None = None
_lua_lock = asyncio.Lock()


async def _ensure_lua_loaded(r: Redis) -> str:
    global _lua_sha

    if _lua_sha:
        return _lua_sha

    async with _lua_lock:
        if _lua_sha:
            return _lua_sha
        _lua_sha = await r.script_load(_LUA_SCRIPT)
        return _lua_sha


async def _parse_lua_response(res: Any) -> tuple[bool, dict]:
    if not isinstance(res, (list, tuple)):
        return False, {"err": res}
    if len(res) == 0:
        return True, {}
    tag = res[0]
    if isinstance(tag, bytes):
        tag = tag.decode()
    if tag == "OK":
        return True, {}
    if tag == "RATE_LIMIT":
        raw_key = res[1]
        raw_limit = res[2]
        raw_reset = res[3]
        key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
        limit = int(raw_limit)
        reset = int(raw_reset)
        return False, {"key": key, "limit": limit, "reset": reset}
    return False, {"err": res}


def rate_limit(
    user_limit: int,
    user_window: int,
    session_limit: int | None = None,
    session_window: int | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:

    def decorator(f: Callable[..., Awaitable[Any]]
                  ) -> Callable[..., Awaitable[Any]]:
        @wraps(f)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            user_id = g.user_id
            session_id = g.session_id

            now = int(time.time())

            keys: list[str] = []
            argv: list[str] = [str(now)]

            user_key = f"user:{user_id}:{f.__name__}:{user_window}"
            keys.append(user_key)
            argv.extend([str(user_limit), str(user_window), str(uuid.uuid4())])

            if session_limit is not None and session_window is not None:
                session_key = (
                    f"session:{session_id}:{f.__name__}:"
                    f"{session_window}"
                )
                keys.append(session_key)
                argv.extend([
                    str(session_limit), str(session_window),
                    str(uuid.uuid4())
                ])

            sha = await _ensure_lua_loaded(redis)
            res = await redis.evalsha(sha, len(keys), *keys, *argv)
            ok, info = await _parse_lua_response(res)
            if not ok:
                return response(
                    error=True,
                    error_msg="RATE_LIMIT",
                    data={
                        "limit": info.get("limit"),
                        "reset": info.get("reset")
                    },
                ), 429
            return await f(*args, **kwargs)

        return wrapped

    return decorator


def ip_rate_limit(
    limit: int, window: int
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:

    def decorator(
        f: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(f)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            forwarded_for = request.headers.get("X-Forwarded-For")
            ip = (
                forwarded_for.split(",")[0].strip()
                if forwarded_for
                else request.remote_addr
            )

            now = int(time.time())

            key = f"ip:{ip}:{f.__name__}:{window}"
            keys = [key]
            argv = [str(now), str(limit), str(window), str(uuid.uuid4())]

            sha = await _ensure_lua_loaded(redis)
            res = await redis.evalsha(sha, len(keys), *keys, *argv)
            ok, info = await _parse_lua_response(res)

            if not ok:
                return response(
                    error=True,
                    error_msg="RATE_LIMIT",
                    data={
                        "limit": info.get("limit"),
                        "reset": info.get("reset")
                    },
                ), 429
            return await f(*args, **kwargs)

        return wrapped

    return decorator
