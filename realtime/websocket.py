
import asyncio
import time
import weakref

import orjson
from quart import websocket, Blueprint
from quart_cors import cors_exempt
from realtime.base import WebSocketState
from realtime.broker import WebSocketBroker, SubCallback
from realtime.auth import ws_token
from realtime.online import send_offline, send_online
from queues.web_push import flush_pending, clear_pending
import typing as t
import logging

logger = logging.getLogger("linkverse.websocket")
bp = Blueprint("websocket", __name__)


# TODO: Task that checks token every 30-60 minutes


class SessionEvent(t.TypedDict):
    type: str
    data: dict[str, t.Any]


class UserEvent(t.TypedDict):
    type: t.Literal["user", "server"]
    event: str
    data: dict[str, t.Any]


async def websocket_send(message: dict) -> None:
    event_message = orjson.dumps(message)
    await websocket.send(event_message.decode())


async def close_connection(
    state: WebSocketState,
    reason: str = "CLOSED"
) -> None:
    if __debug__:
        logger.debug("Closing connection")

    if not state.closed:
        state.closed = True

        state.incoming.shutdown()
        state.auth.shutdown()
        state.sending.shutdown()

        await websocket.close(1000, reason)

        if __debug__:
            logger.debug("Connection closed")


async def receiving(state: WebSocketState) -> None:
    try:
        while not state.closed:
            data = await websocket.receive()

            if __debug__:
                logger.debug("Received message, decoding it...")

            try:
                decoded = orjson.loads(data)
            except orjson.JSONDecodeError:
                continue

            if __debug__:
                logger.debug("Decoded message, putting it in queue...")

            if decoded["type"] == "auth":
                await state.auth.put(decoded)
            else:
                await state.incoming.put(decoded)
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def auth_task(
    state: WebSocketState
) -> None:
    try:
        while not state.closed:
            received = await state.auth.get()

            if __debug__:
                logger.debug("Got auth message")

            result = await ws_token(received["token"], state)
            if result:

                if __debug__:
                    logger.debug("User was authenticated")

                await websocket_send({
                    "event": "success_auth"
                })
                state.auth_event.set()
                continue
            await close_connection(state, "INVALID_TOKEN")
            state.auth.task_done()
    except asyncio.CancelledError:
        return
    except asyncio.QueueShutDown:
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def incoming_task(
    state: WebSocketState
) -> None:
    try:
        while not state.closed:
            received = await state.incoming.get()

            if __debug__:
                logger.debug("Got message with type %s", received["type"])
            if received["type"] == "heartbeat":
                state.heartbeat_event.set()
                data = received.get("data")
                if isinstance(data, dict):
                    last_active = float(data["last_active"])
                    if last_active != state.last_active:
                        await send_online(state.user_id, state.session_id)
                        state.last_active = last_active
                        await clear_pending(state.user_id)
                    if state.last_active < time.time() - 120:
                        await send_offline(state.user_id, state.session_id)
                        await flush_pending(state.user_id)
            state.incoming.task_done()
    except asyncio.CancelledError:
        return
    except asyncio.QueueShutDown:
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def heartbeat_task(
    state: WebSocketState
) -> None:
    try:
        while not state.closed:
            coroutine = state.heartbeat_event.wait()
            await asyncio.wait_for(coroutine, 60)
            if __debug__:
                logger.debug("WS successfully got heartbeat")
            state.heartbeat_event.clear()
            await asyncio.sleep(1)
    except asyncio.TimeoutError:
        await close_connection(state, "HEARTBEAT_TIMEOUT")
    except asyncio.CancelledError:
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def expire_task(
    state: WebSocketState
) -> None:
    try:
        while not state.closed:
            expiration = int(state.token_result["expiration_timestamp"])
            wait_time = max(15, expiration - time.time() - 120)
            if wait_time > 0:
                if __debug__:
                    logger.debug(
                        "Expire task will wait %s "
                        "for token to send refresh_recommended",
                        str(wait_time)
                    )

                try:
                    await asyncio.wait_for(state.auth_event.wait(), wait_time)
                    continue
                except asyncio.TimeoutError:
                    pass

                for _ in range(3):
                    await websocket_send({"event": "refresh_recommended"})
                    try:
                        await asyncio.wait_for(state.auth_event.wait(), 40)
                        break
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(1)
                    await ws_auth(state)
            else:
                await ws_auth(state)
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        if __debug__:
            logger.debug("Expire task was canceled")
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def sending_task(
    state: WebSocketState
) -> None:
    try:
        while not state.closed:
            message = await state.sending.get()

            if __debug__:
                logger.debug("Message is ready to send")

            await state.is_auth.wait()

            if __debug__:
                logger.debug("Sending the message")

            await websocket_send(message)
            state.sending.task_done()
    except asyncio.CancelledError:
        return
    except asyncio.QueueShutDown:
        return
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")


async def create_task(
    state: WebSocketState,
    coroutine: t.Coroutine
) -> None:
    if __debug__:
        logger.debug("Creating task %s", repr(coroutine))

    task = asyncio.create_task(coroutine)
    state.tasks.append(task)


async def ws_auth(
    state: WebSocketState
) -> bool:
    if __debug__:
        logger.debug("Acquiring auth token")

    state.auth_event.clear()
    await websocket_send({
        "event": "please_token"
    })

    try:
        wait_coroutine = state.auth_event.wait()
        await asyncio.wait_for(wait_coroutine, 15)
        state.is_auth.set()

        if __debug__:
            logger.debug("Got correct auth token")

        return True
    except asyncio.TimeoutError:
        await close_connection(state, "AUTH_TIMEOUT")
        state.is_auth.clear()
        return False
    except asyncio.CancelledError:
        return False
    except Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")
    finally:
        state.auth_event.clear()


async def user_event(
    data: UserEvent,
    state: WebSocketState
) -> None:
    if __debug__:
        logger.debug("Got user event with type %s", data["type"])

    if data["type"] == "user":
        await state.sending.put({
            "event": data["event"],
            "data": data["data"]
        })


async def session_event(
    data: SessionEvent,
    state: WebSocketState
) -> None:
    if __debug__:
        logger.debug("Got session event with type %s", data["type"])

    type = data["type"]
    if type == "check_token":
        result = await ws_token(state.token, state, False)
        if not result:
            state.is_auth.clear()
            await ws_auth(state)
    elif type == "session_logout":
        await close_connection(state, "SESSION_CLOSED")


def pubsub_event_wrapper(
    callback: SubCallback,
    state: WebSocketState
) -> SubCallback:
    weak_state = weakref.ref(state)

    async def wrapper(data: dict) -> bool | None:
        state = weak_state()
        if state is None:
            return False
        return await callback(data, state)

    return wrapper


@bp.websocket("/ws")
@cors_exempt
async def ws() -> None:
    if __debug__:
        logger.debug("New connection")

    state = WebSocketState(
        tasks=[],
        incoming=asyncio.Queue(128),
        auth=asyncio.Queue(128),
        sending=asyncio.Queue(128),
        auth_event=asyncio.Event(),
        heartbeat_event=asyncio.Event(),
        is_auth=asyncio.Event(),
        broker=WebSocketBroker()
    )
    await websocket.accept()

    if __debug__:
        logger.debug("Accepted connection, time for main tasks")

    try:
        await create_task(state, receiving(state))
        await create_task(state, auth_task(state))

        if __debug__:
            logger.debug("Starting auth process")

        if not (await ws_auth(state)):
            return

        await create_task(state, incoming_task(state))
        await create_task(state, expire_task(state))
        await create_task(state, heartbeat_task(state))
        await create_task(state, sending_task(state))

        await state.broker.init()

        await state.broker.subscribe(
            f"user:{state.user_id}",
            pubsub_event_wrapper(user_event, state)
        )
        await state.broker.subscribe(
            f"session:{state.session_id}",
            pubsub_event_wrapper(session_event, state)
        )
        await state.broker.subscribe(
            f"session:{state.user_id}",
            pubsub_event_wrapper(session_event, state)
        )

        await create_task(state, state.broker.start())

        await asyncio.gather(*state.tasks, return_exceptions=True)
    except* asyncio.CancelledError:
        pass
    except* asyncio.QueueShutDown:
        pass
    except* Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")
    finally:
        if __debug__:
            logger.debug("Cleaning up resources")
        if not state.closed:
            await close_connection(state, "ABNORMAL_CLOSE")
        if state.is_auth.is_set():
            await send_offline(state.user_id, state.session_id)
            await flush_pending(state.user_id)

        state.incoming.shutdown()
        state.auth.shutdown()
        state.sending.shutdown()
        state.auth_event.clear()
        state.heartbeat_event.clear()
        state.is_auth.clear()
        for task in state.tasks:
            if not task.done():
                task.cancel()

        await state.broker.cleanup()

        await asyncio.gather(*state.tasks, return_exceptions=True)

        if __debug__:
            logger.debug("Cleaned up, letting GC to do its work")
            to_finalize = [
                (state, "State"),
                (state.broker.pubsub, "PubSub"),
                (state.broker, "Broker"),
                (state.incoming, "Incoming queue"),
                (state.sending, "Sending queue"),
                (state.auth, "Auth queue"),
            ]
            for var, desc in to_finalize:
                weakref.finalize(
                    var,
                    lambda desc=desc: logger.debug(
                        "%s was finalized",
                        repr(desc)
                    )
                )
            del to_finalize

        del state.broker
        del state
