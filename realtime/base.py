

import asyncio
from dataclasses import dataclass
import typing as t
from realtime.broker import WebSocketBroker


class ClientPayload(t.TypedDict):
    type: str
    action: str
    data: str


class AuthPayload(t.TypedDict):
    type: t.Literal["auth"]
    token: str


@dataclass
class WebSocketState:
    tasks: list[asyncio.Task[None]]
    incoming: asyncio.Queue[ClientPayload]
    auth: asyncio.Queue[AuthPayload]
    sending: asyncio.Queue[dict]
    auth_event: asyncio.Event
    heartbeat_event: asyncio.Event
    is_auth: asyncio.Event
    broker: WebSocketBroker
    closed: bool = False
    user_id: str | None = None
    token: str | None = None
    token_result: dict[str] | None = None
    session_id: str | None = None
    last_active: int = 0
