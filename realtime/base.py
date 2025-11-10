

import asyncio
from dataclasses import dataclass
import typing as t
from realtime.broker import WebSocketBroker


class ClientPayload(t.TypedDict):
    type: str
    action: str
    data: dict[str, str]


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
    user_id: str
    token: str
    token_result: dict[str, str]
    session_id: str
    last_active: float = 0.0
    closed: bool = False
