from redis.asyncio import Redis
from core import Global
import asyncio
import asyncpg
import ujson
import utils.notifs as notifs
from utils.database import AutoConnection
from collections import defaultdict
import typing as t
from enum import Enum


gb = Global()
redis: Redis = gb.redis
pool: asyncpg.Pool = gb.pool


class SessionActions(int, Enum):
    CHECK_TOKEN = 0
    SESSION_LOGOUT = 1


class SessionMessage(t.TypedDict):
    action: str
    data: t.Any


class RealtimeManager:
    def __init__(self, redis_client: Redis | None = None):
        self.redis_client = redis_client or redis
        self.connection_queues: dict[str, set[asyncio.Queue]] = (
            defaultdict(set)
        )
        self.session_queues: dict[str, set[asyncio.Queue]] = (
            defaultdict(set)
        )
        self.pubsub = self.redis_client.pubsub()

    async def start(self):
        await self.pubsub.psubscribe('events:*')
        await self.pubsub.psubscribe('session_events:*')
        async for message in self.pubsub.listen():
            if message['type'] == 'pmessage':
                channel = message['channel'].decode()
                channel, user_id = channel.split(':')
                handlers = {
                    "session_events": (ujson.loads, self.session_queues),
                    "events": (lambda x: x.decode(), self.connection_queues)
                }
                decoder, queues_dict = handlers[channel]
                data = decoder(message['data'])
                if queues := queues_dict.get(user_id):
                    for queue in queues:
                        await queue.put(data)

    def add_connection(
        self, user_id: str,
        queue: asyncio.Queue,
        session_queue: asyncio.Queue
    ):
        self.connection_queues[user_id].add(queue)
        self.session_queues[user_id].add(session_queue)

    def remove_connection(
        self, user_id: str,
        queue: asyncio.Queue,
        session_queue: asyncio.Queue
    ):
        if user_id in self.connection_queues:
            self.connection_queues[user_id].discard(queue)
            self.session_queues[user_id].discard(session_queue)

            if not self.connection_queues[user_id]:
                del self.connection_queues[user_id]

            if not self.session_queues[user_id]:
                del self.session_queues[user_id]

    async def _publish_to_redis(
        self, user_id: str, message: str | bytes,
        is_session_event: bool = False
    ):
        channel = "events" if not is_session_event else "session_events"
        await self.redis_client.publish(f"{channel}:{user_id}", message)
        return user_id, message

    def _handle_publish_result(self, task: asyncio.Task):
        try:
            task.result()
        except ConnectionError:
            pass
        except Exception as e:
            # TODO: Add error exception to logs
            raise e

    async def session_event(
        self,
        user_id: str,
        action: SessionActions,
        data: t.Any
    ) -> None:
        message = {
            "action": action,
            "data": data
        }
        json_message = ujson.dumps(message)
        task = asyncio.create_task(
            self._publish_to_redis(user_id, json_message, True)
        )
        task.add_done_callback(
            lambda t: self._handle_publish_result(t)
        )

    async def publish_event(
        self,
        user_id: str,
        event: str,
        data: dict
    ) -> None:
        message = {
            "event": event,
            "data": data
        }
        json_message = ujson.dumps(message)
        task = asyncio.create_task(
            self._publish_to_redis(user_id, json_message)
        )
        task.add_done_callback(
            lambda t: self._handle_publish_result(t)
        )

    async def publish_notification(
        self,
        user_id: str,
        to: str,
        type: notifs.NotificationType | str,
        conn: AutoConnection,
        message: str | None = None,
        linked_type: str | None = None,
        linked_id: str | None = None,
        second_linked_id: str | None = None
    ) -> None:
        if user_id == to:
            return

        notification: notifs.Notification = {  # type: ignore
            "from_id": user_id,
            "message": message,
            "type": type
        }
        if linked_type:
            notification["linked_type"] = linked_type
            notification["linked_id"] = linked_id
            if second_linked_id:
                notification["second_linked_id"] = second_linked_id

        await notifs.create_notification(
            to, user_id, type, conn, message,
            linked_type, linked_id, second_linked_id
        )

        await self.publish_event(
            to, "notification", t.cast(dict, notification)
        )
