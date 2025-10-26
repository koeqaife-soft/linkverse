from core import Global
from redis.asyncio import Redis
import asyncpg
import time

gb = Global()
redis: Redis = gb.redis
pool: asyncpg.Pool = gb.pool
SESSION_TTL = 60
ONLINE_THRESHOLD = 120


async def send_online(user_id: str, session_id: str):
    now = time.time()
    pipe = redis.pipeline()
    pipe.setex(f"session:{session_id}:last_active", SESSION_TTL, now)
    pipe.sadd(f"user:{user_id}:sessions", session_id)
    pipe.expire(f"user:{user_id}:sessions", 3600)
    await pipe.execute()


async def send_offline(user_id: str, session_id: str):
    pipe = redis.pipeline()
    pipe.delete(f"session:{session_id}:last_active")
    pipe.srem(f"user:{user_id}:sessions", session_id)
    await pipe.execute()


async def is_online(user_id: str) -> bool:
    session_ids = await redis.smembers(
        f"user:{user_id}:sessions"
    )

    if not session_ids:
        return False

    now = time.time()

    for sid in session_ids:
        sid = sid.decode() if isinstance(sid, bytes) else sid
        last_active = await redis.get(
            f"session:{sid}:last_active"
        )
        if last_active and now - float(last_active) < ONLINE_THRESHOLD:
            return True
        elif not last_active:
            await redis.srem(f"user:{user_id}:sessions", sid)

    return False
