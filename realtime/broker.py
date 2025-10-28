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
        self.subs: dict[str, SubCallback] = {}

    async def subscribe(
        self,
        channel: str,
        callback: SubCallback,
        *args: t.Any
    ) -> None:
        self.subs[channel] = callback
        await self.pubsub.psubscribe(channel)

    async def unsubscribe(
        self,
        channel: str
    ) -> None:
        if channel not in self.subs.keys():
            return
        del self.subs[channel]
        await self.pubsub.punsubscribe(channel)

    async def init(self) -> None:
        self.pubsub = redis.pubsub()
        await self.pubsub.connect()

    async def start(self) -> None:
        if not hasattr(self, 'pubsub'):
            raise RuntimeError("WebSocketBroker not initialized")
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
        if not hasattr(self, 'pubsub'):
            return
        for channel in list(self.subs.keys()):
            await self.unsubscribe(channel)
        await self.pubsub.aclose()


async def publish_event(channel: str, data: dict) -> None:
    await redis.publish(channel, orjson.dumps(data))
