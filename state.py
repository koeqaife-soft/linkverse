import asyncpg
from redis.asyncio import Redis


def load_state(_pool: asyncpg.Pool, _redis: Redis):
    global pool, redis
    pool, redis = _pool, _redis
