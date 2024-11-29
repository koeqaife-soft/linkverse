import asyncio
from core import Status
from dataclasses import asdict
import time
from typing import Any, Awaitable, Callable, TypeVar, overload
from core import _logger, worker_count, get_proc_identity
from aiocache import Cache as AioCache  # type: ignore
from aiocache import RedisCache
from redis import ConnectionError
from aiocache.serializers import PickleSerializer  # type: ignore
import utils.users
import utils.posts
from utils.users import User
from utils.posts import Post
from _types import connection_type
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

    async def delete(self, key: str) -> None:
        async with self.lock:
            self.cache.pop(key, None)

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
        self.cache: RedisCache = AioCache.from_url(url)

        if not isinstance(self.cache, RedisCache):
            raise ValueError("Only Redis cache is supported!")

        self.cache.serializer = PickleSerializer()
        self.redis_working: bool = True
        self.ttl_cache = TTLCache()
        _g._cache = self

    async def ping(self) -> None:
        try:
            await self.cache.get("test_conn")
            await self.redis_status(True)
        except ConnectionError:
            await self.redis_status(False)

    async def init(self) -> None:
        await self.ping()
        asyncio.create_task(self.clear_ttl_timer())
        asyncio.create_task(self.ping_timer())

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

    async def ping_timer(self):
        await asyncio.sleep(get_proc_identity()/4)
        while True:
            interval = 15 if self.redis_working else 1
            await asyncio.sleep(interval)
            await self.ping()

    async def clear_ttl_timer(self):
        while True:
            await asyncio.sleep(60)
            if not self.redis_working:
                await self.ttl_cache._cleanup()

    @overload
    async def _cache(
        self, func: Callable[..., Awaitable[R]]
    ) -> R | None:
        ...

    @overload
    async def _cache(
        self, func: Callable[..., Awaitable[R]],
        no_conn: Callable[..., Awaitable[R]]
    ) -> R:
        ...

    async def _cache(
        self, func: Callable[..., Awaitable[R]],
        no_conn: Callable[..., Awaitable[R]] | None = None
    ) -> R | None:
        async def run_with_fallback(func, no_conn=None):
            if func is None:
                return None
            try:
                return await func()
            except ConnectionError:
                await self.redis_status(False)
                if no_conn:
                    return await no_conn()
                else:
                    return None

        if self.redis_working:
            return await run_with_fallback(func, no_conn)
        else:
            return await run_with_fallback(
                no_conn if no_conn
                else None
            )

    async def get(self, key: str):
        return await self._cache(
            lambda: self.cache.get(key),
            lambda: self.ttl_cache.get(key)
        )

    async def set(self, key: str, value: Any, ttl: int | None = None):
        await self._cache(
            lambda: self.cache.set(key, value, ttl=ttl),
            lambda: self.ttl_cache.set(key, value, 15)
        )

    async def delete(self, key: str):
        await self._cache(
            lambda: self.cache.delete(key),
            lambda: self.ttl_cache.delete(key)
        )


cache_instance: Cache = _g._cache


class users:
    @staticmethod
    async def get_user(
        user_id: str, conn: connection_type,
        _cache_instance: Cache | None = None
    ) -> Status[User | None]:
        cache = _cache_instance or cache_instance
        key = f"user_profile:{user_id}"
        value = await cache.get(key)
        if value is None:
            result = await utils.users.get_user(user_id, conn)
            if not result.success:
                return Status(False, message=result.message)
            assert result.data is not None
            await cache.set(key, asdict(result.data), 600)
            return Status(True, result.data)
        else:
            return Status(True, User(**value))

    @staticmethod
    async def delete_user_cache(
        user_id: str, _cache_instance: Cache | None = None
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
        post_id: str, conn: connection_type,
        _cache_instance: Cache | None = None
    ) -> Status[Post | None]:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"
        value = await cache.get(key)
        if value is None:
            result = await utils.posts.get_post(post_id, conn)
            if not result.success:
                return Status(False, message=result.message)

            assert result.data is not None
            await cache.set(key, asdict(result.data), 15)
            return Status(True, result.data)
        else:
            return Status(True, Post(**value))

    @staticmethod
    async def remove_post_cache(
        post_id: str, _cache_instance: Cache | None = None
    ) -> Status[None]:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"
        value = await cache.get(key)
        if value is not None:
            await cache.delete(key)
        return Status(True)
