import asyncio
from dataclasses import asdict
import time
from typing import Any, TypeVar
from aiocache import Cache as AioCache  # type: ignore
from aiocache import RedisCache
from redis import ConnectionError
from aiocache.serializers import PickleSerializer  # type: ignore
import utils.users
import utils.posts
from utils.users import User
from utils.posts import Post
from core import Global, FunctionError
from utils.database import AutoConnection
from utils.generation import decode_token
from utils.auth import secret_key, check_token
from collections import OrderedDict
from redis.asyncio import Redis
import heapq
import typing as t

R = TypeVar('R')

gb = Global()
redis: Redis = gb.redis


class TTLCache:
    def __init__(self, max_size: int = 5000) -> None:
        self.cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self.read_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()
        self.max_size = max_size

    async def set(self, key: str, value: Any, timeout: float) -> None:
        async with self.write_lock:
            expire_time = time.time() + timeout
            if key in self.cache:
                self.cache.pop(key)
            self.cache[key] = (value, expire_time)
            self.cache.move_to_end(key)

    async def get(self, key: str) -> Any | None:
        item = self.cache.get(key)
        if item is None:
            return None
        value, expire_time = item
        if time.time() < expire_time:
            return value
        else:
            return None

    async def delete(self, key: str) -> None:
        async with self.write_lock:
            self.cache.pop(key, None)

    async def cleanup(self) -> None:
        async with self.write_lock:
            current_time = time.time()

            expired_keys = [
                key for key, (_, expire_time) in self.cache.items()
                if current_time >= expire_time
            ]
            for key in expired_keys:
                self.cache.pop(key, None)

            if len(self.cache) > self.max_size:
                expiring_keys = [
                    (expire_time - current_time, key)
                    for key, (_, expire_time) in self.cache.items()
                ]
                keys_to_delete = [
                    key for _, key in heapq.nsmallest(
                        len(self.cache) - self.max_size, expiring_keys
                    )
                ]
                for key in keys_to_delete:
                    self.cache.pop(key, None)

    async def clear(self) -> None:
        async with self.write_lock:
            self.cache.clear()


class Cache:
    def __init__(self, url: str = "redis://localhost:6379") -> None:
        self.url = url
        self.cache = t.cast(RedisCache, AioCache.from_url(url))

        if not isinstance(self.cache, RedisCache):
            raise ValueError("Only Redis cache is supported!")

        self.cache.serializer = PickleSerializer()
        self.ttl_cache = TTLCache()
        gb._cache = self

    async def init(self) -> None:
        asyncio.create_task(self.clear_ttl_timer())

    async def clear_ttl_timer(self):
        while True:
            await asyncio.sleep(15)
            await self.ttl_cache.cleanup()

    async def get(self, key: str, conn: AutoConnection | None = None) -> Any:
        # Check L1 (connection cache)
        if conn and (cached_l1 := conn.temp_cache.get(key)) is not None:
            return cached_l1

        # Check L2 (local worker cache)
        if (cached_l2 := await self.ttl_cache.get(key)) is not None:
            if conn:
                conn.temp_cache[key] = cached_l2
            return cached_l2

        # Check L3 (Redis cache)
        try:
            if (cached_l3 := await self.cache.get(key)) is not None:
                # Store in L1 for future requests
                if conn:
                    conn.temp_cache[key] = cached_l3

                # Store in L2 with TTL = 5 seconds
                await self.ttl_cache.set(key, cached_l3, 5)
                return cached_l3
        except ConnectionError:
            pass  # Redis connection error, return None

        return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None,
        conn: AutoConnection | None = None
    ) -> None:
        if conn:
            conn.temp_cache[key] = value

        await self.ttl_cache.set(key, value, 10)

        try:
            await self.cache.set(key, value, ttl or 10)
        except ConnectionError:
            pass

    async def delete(
        self, key: str,
        conn: AutoConnection | None = None
    ) -> None:
        if conn:
            conn.temp_cache.pop(key, None)

        await self.ttl_cache.delete(key)
        try:
            await self.cache.delete(key)
        except ConnectionError:
            pass


cache_instance: Cache = gb._cache


class users:
    @staticmethod
    async def get_user(
        user_id: str, conn: AutoConnection,
        minimize_info: bool = False,
        _cache_instance: Cache | None = None
    ) -> User:
        cache = _cache_instance or cache_instance
        key = f"user_profile:{user_id}{":min" if minimize_info else ""}"

        value = await cache.get(key, conn)

        if value is None:
            result = await utils.users.get_user(user_id, conn, minimize_info)
            data = asdict(result)

            await cache.set(key, data, 600, conn)

            return result
        else:
            return User.from_dict(value)

    @staticmethod
    async def delete_user_cache(
        user_id: str, _cache_instance: Cache | None = None
    ) -> None:
        cache = _cache_instance or cache_instance
        key = f"user_profile:{user_id}"
        key2 = f"user_profile:{user_id}:min"
        value = await cache.get(key)
        value2 = await cache.get(key2)
        if value is not None:
            await cache.delete(key)
        if value2 is not None:
            await cache.delete(key2)


class posts:
    @staticmethod
    async def get_post(
        post_id: str, conn: AutoConnection,
        _cache_instance: Cache | None = None
    ) -> Post:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"

        value = await cache.get(key, conn)

        if value is None:
            result = await utils.posts.get_post(post_id, conn)
            data = asdict(result)

            await cache.set(key, data, 15, conn)

            return result
        else:
            return Post.from_dict(value)

    @staticmethod
    async def remove_post_cache(
        post_id: str, _cache_instance: Cache | None = None
    ) -> None:
        cache = _cache_instance or cache_instance
        key = f"posts:{post_id}"
        value = await cache.get(key)
        if value is not None:
            await cache.delete(key)


class auth:
    @staticmethod
    async def check_token(
        token: str, conn: AutoConnection,
        _cache_instance: Cache | None = None
    ) -> dict:

        cache = _cache_instance or cache_instance
        decoded = await decode_token(token, secret_key)
        if not decoded["success"]:
            raise FunctionError(decoded.get("msg"), 401, None)
        elif decoded["is_expired"]:
            raise FunctionError("EXPIRED_TOKEN", 401, None)

        key = f"auth:{decoded["user_id"]}:{decoded["secret"]}"
        value = await cache.get(key, conn)
        if value is None:
            await check_token(token, conn, decoded)
            ttl = decoded["expiration_timestamp"] - int(time.time())
            await cache.set(key, "1", min(max(0, ttl), 60), conn)
        return decoded

    @staticmethod
    async def clear_token_cache(
        decoded: dict,
        _cache_instance: Cache | None = None
    ) -> None:
        cache = _cache_instance or cache_instance
        key = f"auth:{decoded["user_id"]}:{decoded["secret"]}"
        value = await cache.get(key)
        if value is not None:
            await cache.delete(key)

    @staticmethod
    async def clear_all_tokens(
        user_id: str,
        _cache_instance: Cache | None = None
    ) -> None:
        cache = _cache_instance or cache_instance
        pattern = f"auth:{user_id}:*"

        cursor: t.Any = b"0"
        while cursor:
            cursor, keys = await redis.scan(
                cursor=cursor, match=pattern, count=1000
            )
            if keys:
                await redis.delete(*keys)
                for key in keys:
                    await cache.ttl_cache.delete(key)
