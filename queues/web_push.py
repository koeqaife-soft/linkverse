import asyncio
import time
from urllib.parse import urlparse

import aiohttp
from core import Global
from redis.asyncio import Redis
from core import get_proc_identity, server_id
import orjson
from pywebpush import WebPusher, Vapid01
from logging import getLogger
import os
import typing as t
from utils.database import AutoConnection
from utils.notifs import delete_subscription, get_subscriptions
if t.TYPE_CHECKING:
    from utils.realtime import RealtimeManager
from asyncpg import Pool

logger = getLogger("linkverse.web_push")
gb = Global()
redis: Redis = gb.redis
rt_manager: "RealtimeManager" = gb.rt_manager
pool: Pool = gb.pool

REDIS_URL = "redis://localhost:6379"
STREAM_NAME = "webpush_stream"
GROUP_NAME = "webpush_group"
CONSUMER_NAME = f"worker_{get_proc_identity()}_{server_id}"

VAPID_PRIVATE_KEY = Vapid01.from_string(
    private_key=os.environ["VAPID_SECRET"]
)
VAPID_CLAIMS = {"sub": "mailto:koeqaife@sharinflame.com"}


def truncate_message(msg: str, max_len: int = 100) -> str:
    if len(msg) <= max_len:
        return msg
    return msg[:max_len - 1] + "…"


class WebPushNotification(t.TypedDict):
    id: str
    type: str
    username: str
    avatar_url: str
    message: str
    is_reply: bool | None = None


async def enqueue_push(
    user_id: dict, payload: WebPushNotification
) -> None:
    payload["message"] = truncate_message(payload["message"])

    entry = {
        "user_id": orjson.dumps(user_id),
        "payload": orjson.dumps(payload)
    }
    await redis.xadd(
        STREAM_NAME, entry,
        maxlen=50000,
    )


async def send_push(
    subscription: dict, payload: WebPushNotification,
    aiohttp_session: aiohttp.ClientSession
) -> None:
    headers = generate_vapid_headers(subscription)
    pusher = WebPusher(
        subscription, aiohttp_session=aiohttp_session
    )
    response: aiohttp.ClientResponse = await pusher.send_async(
        orjson.dumps(payload).decode(),
        headers=headers,
        ttl=0,
        content_encoding="aes128gcm",
        curl=False
    )
    if response.status == 404 or response.status == 410:
        async with AutoConnection(pool) as conn:
            await delete_subscription(
                payload["session_id"], conn
            )
    else:
        response.raise_for_status()


async def send_pushes(
    user_id: dict, payload: WebPushNotification,
    aiohttp_session: aiohttp.ClientSession,
    conn: AutoConnection
) -> None:
    subscriptions = (await get_subscriptions(user_id, conn)).data
    for sub in subscriptions:
        try:
            await send_push(orjson.loads(sub["raw"]), payload, aiohttp_session)
        except Exception as e:
            logger.exception(e)


async def enqueue_pending(
    user_id: str,
    payload: WebPushNotification,
    aiohttp_session: aiohttp.ClientSession,
    conn: AutoConnection
) -> None:
    if await rt_manager.is_online(user_id):
        _dict = {
            "user_id": user_id,
            "payload": payload
        }
        await redis.rpush(f"pending:{user_id}", orjson.dumps(_dict))
        await redis.expire(f"pending:{user_id}", 3600)
    else:
        await send_pushes(user_id, payload, aiohttp_session, conn)


async def flush_pending(user_id: str):
    if await rt_manager.is_online(user_id):
        return

    key = f"pending:{user_id}"

    while True:
        item = await redis.lpop(key)
        if not item:
            break
        payload = orjson.loads(item)
        await enqueue_push(payload["user_id"], payload["payload"])
    await redis.delete(key)


async def clear_pending(user_id: str):
    await redis.delete(f"pending:{user_id}")


async def push_worker():
    try:
        await redis.xgroup_create(
            STREAM_NAME,
            GROUP_NAME,
            id='0',
            mkstream=True
        )
    except Exception:
        pass

    aiohttp_session = aiohttp.ClientSession()

    while True:
        msgs = await redis.xreadgroup(
            GROUP_NAME,
            CONSUMER_NAME,
            {STREAM_NAME: ">"},
            count=25,
            block=60 * 60 * 1000
        )
        if not msgs:
            continue
        async with AutoConnection(pool) as conn:
            tasks: list[asyncio.Task[None]] = []
            for stream, entries in msgs:
                for msg_id, data in entries:
                    user_id: dict = orjson.loads(data[b'user_id'])
                    payload: WebPushNotification = orjson.loads(
                        data[b'payload']
                    )
                    try:
                        tasks.append(asyncio.create_task(enqueue_pending(
                            user_id,
                            payload,
                            aiohttp_session,
                            conn
                        )))
                    except Exception as e:
                        logger.exception(e)
                    finally:
                        await redis.xack(STREAM_NAME, GROUP_NAME, msg_id)
            await asyncio.gather(*tasks, return_exceptions=True)

        await asyncio.sleep(0.01)


def generate_vapid_headers(subscription: dict) -> dict:
    headers = {}
    vapid_claims = VAPID_CLAIMS.copy()

    if not vapid_claims.get("aud"):
        url = urlparse(subscription.get("endpoint"))
        vapid_claims["aud"] = f"{url.scheme}://{url.netloc}"

    if (
        not vapid_claims.get("exp")
        or int(vapid_claims.get("exp")) < int(time.time())
    ):
        vapid_claims["exp"] = int(time.time()) + 12*60*60

    if isinstance(VAPID_PRIVATE_KEY, Vapid01):
        vv = VAPID_PRIVATE_KEY
    elif os.path.isfile(VAPID_PRIVATE_KEY):
        vv = Vapid01.from_file(private_key_file=VAPID_PRIVATE_KEY)
    else:
        vv = Vapid01.from_string(private_key=VAPID_PRIVATE_KEY)

    vapid_headers = vv.sign(vapid_claims)
    headers.update(vapid_headers)
    return headers
