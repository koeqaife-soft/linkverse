
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
    if not state.closed:
        state.closed = True
        for task in state.tasks:
            task.cancel()
        await websocket.close(1000, reason)


async def receiving(state: WebSocketState) -> None:
    try:
        while True:
            data = await websocket.receive()
            try:
                decoded = orjson.loads(data)
            except orjson.JSONDecodeError:
                continue

            if decoded["type"] == "auth":
                await state.auth.put(decoded)
            else:
                await state.incoming.put(decoded)
    except asyncio.CancelledError:
        return


async def auth_task(
    state: WebSocketState
) -> None:
    try:
        while True:
            received = await state.auth.get()
            result = await ws_token(received["token"], state)
            if result:
                await websocket_send({
                    "event": "success_auth"
                })
                state.auth_event.set()
                continue
            await close_connection(state, "INVALID_TOKEN")
    except asyncio.CancelledError:
        return


async def incoming_task(
    state: WebSocketState
) -> None:
    try:
        while True:
            received = await state.incoming.get()

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
    except asyncio.CancelledError:
        return


async def heartbeat_task(
    state: WebSocketState
) -> None:
    while True:
        try:
            coroutine = state.heartbeat_event.wait()
            await asyncio.wait_for(coroutine, 60)
            state.heartbeat_event.clear()
        except asyncio.TimeoutError:
            await close_connection(state, "HEARTBEAT_TIMEOUT")
        except asyncio.CancelledError:
            return


async def expire_task(
    state: WebSocketState
) -> None:
    try:
        while True:
            expiration = int(state.token_result["expiration_timestamp"])
            wait_time = max(0, expiration - time.time() - 120)
            if wait_time > 0:
                coroutine = state.auth_event.wait()
                try:
                    await asyncio.wait_for(coroutine, wait_time)
                    continue
                except asyncio.TimeoutError:
                    pass

                for _ in range(3):
                    await websocket_send({"event": "refresh_recommended"})
                    coroutine = state.auth_event.wait()
                    try:
                        await asyncio.wait_for(coroutine, 40)
                        break
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(1)
                    await ws_auth(state)
    except asyncio.CancelledError:
        return


async def sending_task(
    state: WebSocketState
) -> None:
    try:
        while True:
            message = await state.sending.get()
            print("Got message:", message)
            await state.is_auth.wait()
            print("Sending message:", message)
            await websocket_send(message)
    except asyncio.CancelledError:
        return


async def create_task(
    state: WebSocketState,
    coroutine: t.Coroutine
) -> None:
    print("Creating task:", coroutine)
    task = asyncio.create_task(coroutine)
    state.tasks.append(task)


async def ws_auth(
    state: WebSocketState
) -> bool:
    print("Starting auth process")
    state.auth_event.clear()
    await websocket_send({
        "event": "please_token"
    })

    try:
        wait_coroutine = state.auth_event.wait()
        await asyncio.wait_for(wait_coroutine, 15)
        state.is_auth.set()
        return True
    except asyncio.TimeoutError:
        await close_connection(state, "AUTH_TIMEOUT")
        state.is_auth.clear()
        return False
    except asyncio.CancelledError:
        return False
    finally:
        state.auth_event.clear()


async def user_event(
    data: UserEvent,
    state: WebSocketState
) -> None:
    print("User event received:", data)
    if data["type"] == "user":
        print("Processing user event:", data)
        await state.sending.put({
            "event": data["event"],
            "data": data["data"]
        })
        print("User event processed")


async def session_event(
    data: SessionEvent,
    state: WebSocketState
) -> None:
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
    print("Creating pubsub event wrapper")
    weak_state = weakref.ref(state)

    async def wrapper(data: dict) -> bool | None:
        print("Pubsub event received:", data)
        state = weak_state()
        if state is None:
            return False
        print("Calling callback with data:", data)
        return await callback(data, state)

    return wrapper


@bp.websocket("/ws")
@cors_exempt
async def ws() -> None:
    print("WebSocket connection attempt")
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

    try:
        await create_task(state, receiving(state))
        await create_task(state, auth_task(state))

        if not (await ws_auth(state)):
            return

        await create_task(state, incoming_task(state))
        await create_task(state, expire_task(state))
        await create_task(state, heartbeat_task(state))
        await create_task(state, sending_task(state))

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
    except* Exception as e:
        logger.exception(e)
        await close_connection(state, "INTERNAL_ERROR")
    finally:
        if not state.closed:
            await close_connection(state, "ABNORMAL_CLOSE")
        if state.is_auth.is_set():
            await send_offline(state.user_id, state.session_id)
            await flush_pending(state.user_id)
        await state.broker.cleanup()
        del state.broker
        del state
