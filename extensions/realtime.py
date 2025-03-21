import time
from quart import Blueprint, websocket, g, Quart
from core import Global, FunctionError
import asyncpg
import asyncio
from quart_cors import cors_exempt
import utils.auth as auth
from utils.database import AutoConnection
import utils.realtime as realtime
from utils.realtime import SessionActions, SessionMessage
import ujson

bp = Blueprint('realtime', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: realtime.RealtimeManager = gb.rt_manager


async def sending(queue: asyncio.Queue):
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
            decoded: dict = ujson.loads(data)
        except ujson.JSONDecodeError:
            continue

        await g.incoming_queue.put(decoded)
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
    event_message = ujson.dumps({
        "event": "please_token"
    })
    await websocket.send(event_message)
    try:
        data = await asyncio.wait_for(
            g.incoming_queue.get(), timeout=60
        )
        token = data.get("token")
        success = await ws_auth(token)
        if success:
            event_message = ujson.dumps({
                "event": "success_auth"
            })
            await websocket.send(event_message)
            return True
    except ujson.JSONDecodeError:
        await websocket.close(1008, "AUTH_DATA_INCORRECT")
    except asyncio.TimeoutError:
        await websocket.close(1008, "AUTH_REQUIRED")


async def expire_timeout():
    expiration = int(g.token_result["expiration_timestamp"])
    wait_time = max(0, expiration - time.time() - 120)

    if wait_time > 0:
        try:
            await asyncio.sleep(wait_time)
            event_message = ujson.dumps({
                "event": "refresh_recommended"
            })
            await websocket.send(event_message)
            await asyncio.sleep(120)
        except asyncio.CancelledError:
            return

    await ws_auth(g.token)


async def session_actions(queue: asyncio.Queue[SessionMessage]):
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
        finally:
            queue.task_done()


@bp.websocket('/ws')
@cors_exempt
async def ws():
    await websocket.accept()
    g.incoming_queue = asyncio.Queue()
    queue = asyncio.Queue()
    session_queue = asyncio.Queue()

    producer = asyncio.create_task(sending(queue))
    consumer = asyncio.create_task(receiving())

    auth_success = await wait_auth()
    if not auth_success:
        return

    rt_manager.add_connection(g.user_id, queue, session_queue)

    try:

        actions = asyncio.create_task(session_actions(session_queue))
        await asyncio.gather(producer, consumer, actions)
    finally:
        rt_manager.remove_connection(g.user_id, queue, session_queue)


def load(app: Quart):
    app.register_blueprint(bp)
