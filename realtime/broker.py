from core import Global
from redis.asyncio import Redis
import typing as t
import orjson
import weakref

gb = Global()
redis: Redis = gb.redis

type SubCallback = t.Callable[..., t.Awaitable[bool | None]]


def create_weak_wrapper(
    func: SubCallback,
    *call_args: t.Any
) -> SubCallback:
    if hasattr(func, '__self__'):
        weak_func = weakref.WeakMethod(func)
    else:
        weak_func = weakref.ref(func)

    async def wrapper(
        *args: t.Any
    ) -> bool | None:
        strong_func = weak_func()
        if strong_func is None:
            return False
        return await strong_func(*args, *call_args)

    return wrapper


class WebSocketBroker:
    def __init__(
        self
    ) -> None:
        self.subs: dict[str, SubCallback] = {}
        self.pubsub = redis.pubsub()

    async def subscribe(
        self,
        channel: str,
        callback: SubCallback,
        *args: t.Any
    ) -> None:
        self.subs[channel] = create_weak_wrapper(callback, *args)
        await self.pubsub.psubscribe(channel)

    async def unsubscribe(
        self,
        channel: str
    ) -> None:
        if channel not in self.subs.keys():
            return
        del self.subs[channel]
        await self.pubsub.punsubscribe(channel)

    async def start(self) -> None:
        async for message in self.pubsub.listen():
            if message['type'] == 'pmessage':
                channel: str = message['channel'].decode()
                data: dict = orjson.loads(message['data'])

                sub = self.subs.get(channel)
                if not sub:
                    continue

                result = await sub(data)
                if result is False:
                    await self.unsubscribe(channel)

    async def cleanup(self) -> None:
        await self.pubsub.aclose()
        self.subs.clear()


async def publish_event(channel: str, data: dict) -> None:
    await redis.publish(channel, orjson.dumps(data))
