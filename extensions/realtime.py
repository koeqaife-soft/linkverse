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
from utils.notifs import subscribe
import orjson
import typing as t
from queues.web_push import flush_pending, clear_pending

bp = Blueprint("realtime", __name__)
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
    session_id: str
    tasks: dict[str, asyncio.Task]
    closed: bool
    last_active: int


g: GlobalContext = untyped_g


async def websocket_send(message: dict) -> None:
    event_message = orjson.dumps(message)
    await websocket.send(event_message.decode())


async def sending() -> None:
    queue: asyncio.Queue = g.queues["sending"]
    while True:
        data = await queue.get()
        if data is None:
            queue.task_done()
            break
        try:
            await websocket.send(data)
        except Exception:
            break
        finally:
            queue.task_done()


async def receiving() -> None:
    while True:
        try:
            data = await websocket.receive()
        except Exception:
            break
        try:
            decoded: dict = orjson.loads(data)
        except orjson.JSONDecodeError:
            continue

        if decoded.get("type") == "auth":
            await g.queues["auth"].put(decoded)
            continue

        if decoded.get("action") == "update_token":
            if not decoded.get("token"):
                continue
            await ws_auth(decoded["token"])
            continue

        await g.queues["incoming"].put(decoded)


async def ws_auth(
    token: str | None,
    wait_on_fail: bool = False
) -> bool | None:
    if token is None:
        await close_connection("INVALID_TOKEN")
        return None
    try:
        async with AutoConnection(pool) as conn:
            result = await auth.check_token(token, conn)
            g.token = token
            g.token_result = result.data
    except FunctionError as e:
        if not wait_on_fail:
            await close_connection(e.message)
        else:
            await wait_auth()
        return None

    if hasattr(g, "expire_task") and g.expire_task is not None:
        try:
            g.expire_task.cancel()
        except Exception:
            pass

    g.expire_task = asyncio.create_task(expire_timeout())
    g.user_id = result.data["user_id"]
    g.session_id = result.data["session_id"]
    return True


async def wait_auth() -> bool | None:
    queue: asyncio.Queue = g.queues["auth"]
    await websocket_send({"event": "please_token"})
    try:
        data = await asyncio.wait_for(queue.get(), timeout=60)
        token = data.get("token")
        success = await ws_auth(token)
        if success:
            await websocket_send({"event": "success_auth"})
            return True
        await close_connection("AUTH_DATA_INCORRECT")
    except orjson.JSONDecodeError:
        await close_connection("AUTH_DATA_INCORRECT")
    except asyncio.TimeoutError:
        await close_connection("AUTH_REQUIRED")
    finally:
        try:
            queue.task_done()
        except Exception:
            pass
    return None


async def expire_timeout() -> None:
    try:
        expiration = int(g.token_result["expiration_timestamp"])
        wait_time = max(0, expiration - time.time() - 120)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            for _ in range(3):
                await websocket_send({"event": "refresh_recommended"})
                await asyncio.sleep(40)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        return
    await ws_auth(g.token)


async def session_actions() -> None:
    queue: asyncio.Queue = g.queues["session"]
    while True:
        data = await queue.get()
        if data is None:
            queue.task_done()
            break
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
                    await close_connection("SESSION_CLOSED")
                    break
        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()


async def incoming_handler() -> None:
    queue: asyncio.Queue = g.queues["incoming"]
    while True:
        data = await queue.get()
        if data is None:
            queue.task_done()
            break
        try:
            if data.get("type") == "heartbeat":
                last_active: int = data.get("last_active")
                if last_active is not None:
                    if last_active != g.last_active:
                        await rt_manager.send_online(g.user_id, g.session_id)
                        g.last_active = last_active
                        await clear_pending(g.user_id)
                    if g.last_active < time.time() - 120:
                        await rt_manager.send_offline(g.user_id, g.session_id)
                        await flush_pending(g.user_id)
            elif data.get("type") == "push_subscription":
                sub = data.get("data")
                if sub:
                    async with AutoConnection(pool) as conn:
                        await subscribe(g.user_id, g.session_id, sub, conn)
        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()


async def close_connection(reason: str = "CLOSING") -> None:
    if getattr(g, "closed", False):
        return
    g.closed = True
    try:
        if hasattr(g, "expire_task") and g.expire_task is not None:
            try:
                g.expire_task.cancel()
            except Exception:
                pass
    except Exception:
        pass

    try:
        tasks = getattr(g, "tasks", {})
        for _name, _task in list(tasks.items()):
            try:
                _task.cancel()
            except Exception:
                pass
    except Exception:
        tasks = {}

    try:
        queues = getattr(g, "queues", {})
        for q in queues.values():
            try:
                q.put_nowait(None)
            except Exception:
                try:
                    await q.put(None)
                except Exception:
                    pass
    except Exception:
        pass

    try:
        await asyncio.gather(
            *[t for t in tasks.values() if t is not None],
            return_exceptions=True
        )
    except Exception:
        pass

    try:
        await websocket.close(1000, reason)
    except Exception:
        pass

    try:
        if getattr(g, "user_id", None) is not None:
            try:
                rt_manager.remove_connection(
                    g.user_id, g.queues.get("sending"), g.queues.get("session")
                )
            except Exception:
                pass
    except Exception:
        pass

    await rt_manager.send_offline(g.user_id, g.session_id)
    await flush_pending(g.user_id)


@bp.websocket("/ws")
@cors_exempt
async def ws() -> None:
    await websocket.accept()
    g.last_active = time.time()
    g.queues = {
        "incoming": asyncio.Queue(),
        "auth": asyncio.Queue(),
        "sending": asyncio.Queue(),
        "session": asyncio.Queue(),
    }
    g.tasks = {}
    g.closed = False

    producer = asyncio.create_task(sending())
    consumer = asyncio.create_task(receiving())

    g.tasks["producer"] = producer
    g.tasks["consumer"] = consumer

    auth_success = await wait_auth()
    if not auth_success:
        await close_connection("AUTH_FAILED")
        return

    rt_manager.add_connection(
        g.user_id, g.queues["sending"], g.queues["session"]
    )

    try:
        actions = asyncio.create_task(session_actions())
        incoming = asyncio.create_task(incoming_handler())
        g.tasks["actions"] = actions
        g.tasks["incoming"] = incoming
        await asyncio.gather(producer, consumer, actions, incoming)
    finally:
        await close_connection("NORMAL_CLOSE")


def load(app: Quart) -> None:
    app.register_blueprint(bp)
