import asyncio
from core import Status
from dataclasses import asdict
import time
from typing import Any, Awaitable, Callable, TypeVar, overload
from core import _logger, worker_count, get_proc_identity
from aiocache import Cache as AioCache  # type: ignore
from redis import ConnectionError
from aiocache.serializers import PickleSerializer  # type: ignore
import utils.users
import utils.posts
from utils.users import User
from utils.posts import Post
from _types import connection_type
from asyncpg import Pool
from core import Global

R = TypeVar('R')

worker_id = get_proc_identity()
_g = Global()


class TTLCache:
    def __init__(self) -> None:
        self.cache: dict[str, tuple[Any, float]] = {}
        self.lock = asyncio.Lock()

    async def set(self, key: str, value: Any, timeout: float) -> None:
        async with self.lock:
            expire_time = time.time() + timeout
            self.cache[key] = (value, expire_time)
            await self._cleanup()

    async def get(self, key: str) -> Any | None:
        async with self.lock:
            value, expire_time = self.cache.get(key, (None, 0.0))
            if value is not None and time.time() < expire_time:
                return value
            else:
                self.cache.pop(key, None)
                return None

    async def _cleanup(self) -> None:
        current_time = time.time()
        keys_to_delete = [
            key for key, (_, expire_time) in self.cache.items()
            if current_time >= expire_time
        ]
        for key in keys_to_delete:
            self.cache.pop(key)

    async def clear(self) -> None:
        async with self.lock:
            self.cache.clear()


class Cache:
    def __init__(self, url: str = "redis://localhost:6379") -> None:
        self.url = url
        self.cache = AioCache.from_url(url)
        self.cache.serializer = PickleSerializer()
        self.redis_working: bool = True
        self.ttl_cache = TTLCache()
        _g._cache = self

    async def init(self) -> None:
        asyncio.create_task(self.clear_ttl_timer())
        try:
            await self.cache.set("test_conn", "value", ttl=1)
            await self.redis_status(True)
        except ConnectionError:
            await self.redis_status(False)

    async def redis_status(self, status: bool) -> None:
        if self.redis_working != status:
            self.redis_working = status
            await self.ttl_cache.clear()

            worker_info = (
                f" ({worker_id}/{worker_count})"
                if worker_id != 0 else ""
            )
            log_message = (
                "Redis connected!" if status
                else "Failed to connect to Redis!"
            )
            if _logger:
                log_func = _logger.info if status else _logger.warning
                log_func(log_message + worker_info)

    async def clear_ttl_timer(self):
        while True:
            await asyncio.sleep(60)
            if not self.redis_working:
                await self.ttl_cache._cleanup()

    @overload
    async def _cache(
        self, func: Awaitable[R]
    ) -> R | None:
        ...

    @overload
    async def _cache(
        self, func: Awaitable[R], no_conn: Callable[..., Awaitable[R]]
    ) -> R:
        ...

    async def _cache(
        self, func: Awaitable[R],
        no_conn: Callable[..., Awaitable[R]] | None = None
    ) -> R | None:
        try:
            r = await func
            await self.redis_status(True)
        except ConnectionError:
            if no_conn is not None:
                r = await no_conn()
            else:
                r = None
            await self.redis_status(False)
        return r

    async def get(self, key: str):
        return await self._cache(
            self.cache.get(key),
            lambda: self.ttl_cache.get(key)
        )

    async def set(self, key: str, value: Any, ttl: int | None = None):
        await self._cache(
            self.cache.set(key, value, ttl=ttl),
            lambda: self.ttl_cache.set(key, value, 15)
        )

    async def delete(self, key: str):
        await self._cache(self.cache.delete(key))


class AutoConnection:
    def __init__(self, pool: Pool) -> None:
        self.pool = pool
        self._conn = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        if self._conn is not None:
            await self.pool.release(self._conn)

    async def create_conn(self, **kwargs):
        if self._conn is not None and not self._conn.is_closed():
            return self._conn
        self._conn = await self.pool.acquire(**kwargs)
        return self._conn


cache_instance: Cache = _g._cache
_connection_type = connection_type | Pool | AutoConnection


class _connection:
    def __init__(self, conn: _connection_type) -> None:
        self.conn = conn
        self._conn_proxy = None

    async def __aenter__(self):
        if isinstance(self.conn, connection_type):
            return self.conn
        if isinstance(self.conn, AutoConnection):
            return await self.conn.create_conn()
        else:
            self._conn_proxy = await self.conn.acquire()
            return self._conn_proxy

    async def __aexit__(self, *exc):
        if self._conn_proxy is not None:
            await self.conn.release(self._conn_proxy)


class users:
    @staticmethod
    async def get_user(
        user_id: int, conn: _connection_type,
        _cache_instance: Cache | None = None
    ) -> Status[User | None]:
        cache = _cache_instance or cache_instance
        key = f"user_profile:{user_id}"
        value = await cache.get(key)
        if value is None:
            async with _connection(conn) as db:
                result = await utils.users.get_user(user_id, db)
                if not result.success:
                    return Status(False, message=result.message)
            assert result.data is not None
            await cache.set(key, asdict(result.data), 600)
            return Status(True, result.data)
        else:
            return Status(True, User(**value))

    @staticmethod
    async def delete_user_cache(
        user_id: int, _cache_instance: Cache | None = None
    ) -> Status[None]:
        cache = _cache_instance or cache_instance
        key = f"user_profile:{user_id}"
        value = await cache.get(key)
        if value is not None:
            await cache.delete(key)
        return Status(True)


class posts:
    @staticmethod
    async def get_post(
        post_id: int, conn: _connection_type,
        _cache_instance: Cache | None = None
    ) -> Status[Post | None]:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"
        value = await cache.get(key)
        if value is None:
            async with _connection(conn) as db:
                result = await utils.posts.get_post(post_id, db)
                if not result.success:
                    return Status(False, message=result.message)

                assert result.data is not None
                await cache.set(key, asdict(result.data), 15)
                return Status(True, result.data)
        else:
            return Status(True, Post(**value))

    @staticmethod
    async def remove_post_cache(
        post_id: int, _cache_instance: Cache | None = None
    ) -> Status[None]:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"
        value = await cache.get(key)
        if value is not None:
            await cache.delete(key)
        return Status(True)
