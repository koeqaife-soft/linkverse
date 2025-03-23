import time
from quart import Blueprint, websocket, Quart
from quart import g as untyped_g
from core import Global, FunctionError
import asyncpg
import asyncio
from quart_cors import cors_exempt
import utils.auth as auth
from utils.database import AutoConnection
import utils.realtime as realtime
from utils.realtime import SessionActions, SessionMessage
import orjson
import typing as t

bp = Blueprint('realtime', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: realtime.RealtimeManager = gb.rt_manager


class Queues(t.TypedDict):
    incoming: asyncio.Queue[dict]
    auth: asyncio.Queue[dict]
    sending: asyncio.Queue[t.Any]
    session: asyncio.Queue[SessionMessage]


class GlobalContext:
    queues: Queues
    token: str
    token_result: dict
    expire_task: asyncio.Task
    user_id: str


g: GlobalContext = untyped_g


async def websocket_send(message: dict):
    event_message = orjson.dumps(message)
    await websocket.send(event_message.decode())


async def sending():
    queue = g.queues["sending"]
    while True:
        data = await queue.get()
        try:
            await websocket.send(data)
        finally:
            queue.task_done()


async def receiving():
    while True:
        data = await websocket.receive()
        try:
            decoded: dict = orjson.loads(data)
        except orjson.JSONDecodeError:
            continue

        if decoded.get("type") == "auth":
            await g.queues["auth"].put(decoded)
            continue

        await g.queues["incoming"].put(decoded)
        if decoded.get("action") == "update_token":
            if not decoded.get("token"):
                continue
            await ws_auth(decoded["token"])


async def ws_auth(
    token: str | None,
    wait_on_fail: bool = False
):
    if token is None:
        await websocket.close(1008, "INVALID_TOKEN")
        return
    try:
        async with AutoConnection(pool) as conn:
            result = await auth.check_token(token, conn)
            g.token = token
            g.token_result = result.data
    except FunctionError as e:
        if not wait_on_fail:
            await websocket.close(1008, e.message)
        else:
            await wait_auth()
        return

    if hasattr(g, "expire_task"):
        g.expire_task.cancel()

    g.expire_task = asyncio.create_task(expire_timeout())

    g.user_id = result.data["user_id"]
    return True


async def wait_auth():
    queue = g.queues["auth"]
    await websocket_send({
        "event": "please_token"
    })
    try:
        data = await asyncio.wait_for(
            queue.get(), timeout=60
        )
        token = data.get("token")
        success = await ws_auth(token)
        if success:
            await websocket_send({
                "event": "success_auth"
            })
            return True
        else:
            await websocket.close(1008, "AUTH_DATA_INCORRECT")
    except orjson.JSONDecodeError:
        await websocket.close(1008, "AUTH_DATA_INCORRECT")
    except asyncio.TimeoutError:
        await websocket.close(1008, "AUTH_REQUIRED")


async def expire_timeout():
    expiration = int(g.token_result["expiration_timestamp"])
    wait_time = max(0, expiration - time.time() - 120)

    if wait_time > 0:
        try:
            await asyncio.sleep(wait_time)
            await websocket_send({
                "event": "refresh_recommended"
            })
            await asyncio.sleep(120)
        except asyncio.CancelledError:
            return

    await ws_auth(g.token)


async def session_actions():
    queue = g.queues["session"]
    while True:
        data = await queue.get()
        try:
            checks = {
                "session": lambda: (
                    data.get("data") is None
                    or data["data"] == g.token_result["session_id"]
                )
            }
            if data["action"] == SessionActions.CHECK_TOKEN:
                if checks["session"]():
                    await ws_auth(g.token, True)
            elif data["action"] == SessionActions.SESSION_LOGOUT:
                if checks["session"]():
                    await websocket.close(1008, "SESSION_CLOSED")
        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()


@bp.websocket('/ws')
@cors_exempt
async def ws():
    await websocket.accept()
    g.queues = {
        "incoming": asyncio.Queue(),
        "auth": asyncio.Queue(),
        "sending": asyncio.Queue(),
        "session": asyncio.Queue()
    }

    producer = asyncio.create_task(sending())
    consumer = asyncio.create_task(receiving())

    auth_success = await wait_auth()
    if not auth_success:
        return

    rt_manager.add_connection(
        g.user_id, g.queues["sending"], g.queues["session"]
    )

    try:
        actions = asyncio.create_task(session_actions())
        await asyncio.gather(producer, consumer, actions)
    finally:
        rt_manager.remove_connection(
            g.user_id, g.queues["sending"], g.queues["session"]
        )


def load(app: Quart):
    app.register_blueprint(bp)
