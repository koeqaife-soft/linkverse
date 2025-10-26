from core import Global
from redis.asyncio import Redis
import typing as t
import orjson

gb = Global()
redis: Redis = gb.redis

type SubCallback = t.Callable[..., t.Awaitable[bool | None]]


class WebSocketBroker:
    def __init__(
        self
    ) -> None:
        self.subs: dict[str, tuple[SubCallback, tuple[t.Any, ...]]] = {}
        self.pubsub = redis.pubsub()

    async def subscribe(
        self,
        channel: str,
        callback: SubCallback,
        user_data: tuple[t.Any, ...] = ()
    ) -> None:
        self.subs[channel] = (callback, user_data)
        await self.pubsub.psubscribe(channel)

    async def unsubscribe(
        self,
        channel: str
    ) -> None:
        if "channel" not in self.subs.keys():
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
                callback, user_data = sub

                result = await callback(data, *user_data)
                if result is False:
                    await self.unsubscribe(result)


async def publish_event(channel: str, data: dict) -> None:
    await redis.publish(channel, orjson.dumps(data))
