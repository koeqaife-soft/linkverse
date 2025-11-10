import asyncio
import typing as t
import orjson
import logging
from state import redis

logger = logging.getLogger("linkverse.broker")

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

        try:
            async for message in self.pubsub.listen():
                if __debug__:
                    logger.debug("Broker got message from pub/sub")

                if not message or not isinstance(message, dict):
                    await asyncio.sleep(0.1)
                    continue

                if message['type'] == 'pmessage':
                    channel: str = message['channel'].decode()
                    try:
                        data: dict = orjson.loads(message['data'])

                        sub = self.subs.get(channel)
                        if sub:
                            result = await sub(data)
                            if result is False:
                                await self.unsubscribe(channel)

                    except Exception as e:
                        logger.exception(e)

                await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass

    async def cleanup(self) -> None:
        if not hasattr(self, 'pubsub'):
            return
        for channel in list(self.subs.keys()):
            await self.unsubscribe(channel)
        await self.pubsub.aclose()


async def publish_event(channel: str, data: dict) -> None:
    await redis.publish(channel, orjson.dumps(data))
