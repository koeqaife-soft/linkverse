
import asyncio
import time

import orjson
from quart import websocket, Blueprint
from quart_cors import cors_exempt
from realtime.base import WebSocketState
from realtime.broker import WebSocketBroker
from realtime.auth import ws_token
from realtime.online import send_offline, send_online
from queues.web_push import flush_pending, clear_pending
import typing as t

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
        await websocket.close(1000, reason)
        state.closed = True


async def receiving(state: WebSocketState) -> None:
    while True:
        try:
            data = await websocket.receive()
        except asyncio.CancelledError:
            break

        try:
            decoded = orjson.loads(data)
        except orjson.JSONDecodeError:
            continue

        if decoded["type"] == "auth":
            await state.auth.put(decoded)
        else:
            await state.incoming.put(decoded)


async def auth_task(
    state: WebSocketState
) -> None:
    while True:
        try:
            received = await state.auth.get()
        except asyncio.CancelledError:
            break

        result = await ws_token(received["token"], state)
        if result:
            await websocket_send({
                "event": "success_auth"
            })
            state.auth_event.set()
            continue
        await close_connection(state, "INVALID_TOKEN")


async def incoming_task(
    state: WebSocketState
) -> None:
    while True:
        try:
            received = await state.incoming.get()
        except asyncio.CancelledError:
            break

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
            break


async def expire_task(
    state: WebSocketState
) -> None:
    while True:
        try:
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
            break


async def sending_task(
    state: WebSocketState
) -> None:
    while True:
        try:
            message = state.sending.get()
        except asyncio.CancelledError:
            break
        await state.is_auth.wait()
        await websocket_send(message)


async def create_task(
    state: WebSocketState,
    coroutine: t.Coroutine
) -> None:
    task = asyncio.create_task(coroutine)
    state.tasks.append(task)


async def ws_auth(
    state: WebSocketState
) -> bool:
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
    finally:
        state.auth_event.clear()


async def user_event(
    data: UserEvent,
    state: WebSocketState
) -> None:
    if data["type"] == "user":
        await websocket_send({
            "event": data["event"],
            "data": data["data"]
        })


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


@bp.websocket("/ws")
@cors_exempt
async def ws() -> None:
    state = WebSocketState(
        tasks=[],
        incoming=asyncio.Queue(),
        auth=asyncio.Queue(),
        sending=asyncio.Queue(),
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

        user_data = (state,)
        await state.broker.subscribe(
            f"user:{state.user_id}",
            user_event,
            user_data
        )
        await state.broker.subscribe(
            f"session:{state.session_id}",
            session_event,
            user_data
        )
        await state.broker.subscribe(
            f"session:{state.user_id}",
            session_event,
            user_data
        )

        await create_task(state, state.broker.start())

        await asyncio.gather(*state.tasks)
    except asyncio.CancelledError:
        pass
    finally:
        if state.is_auth.is_set():
            await send_offline(state.user_id, state.session_id)
            await flush_pending(state.user_id)
