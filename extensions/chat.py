
from quart import Blueprint, Quart, Response, g

from core import response, route, FunctionError
from utils.database import AutoConnection
from utils.rate_limiting import rate_limit
import utils.chat as chat
from utils.cache import users as cache_users
from state import pool


bp = Blueprint('chat', __name__)


"""
REST API:

GET /users/me/channels      -> Get chats
TODO: GET /channel/<id>/messages  -> Get messages
POST /channel/<id>/messages -> Create message
POST /user/<id>/messages     -> Create channel and message
"""


@route(bp, "/users/me/channels", methods=["GET"])
@rate_limit(30, 60)
async def get_user_channels() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await chat.get_user_channels(g.user_id, conn)
        for channel in result:
            if channel["type"] == "direct":
                member_ids = channel["members"]
                channel["members"] = []
                for member_id in member_ids:
                    if member_id == g.user_id:
                        continue
                    user = await cache_users.get_user(
                        member_id, conn,
                        minimize_info=True
                    )
                    channel["members"].append(user.dict)  # type: ignore

    return response(data={
        "channels": result
    }), 200


@route(bp, "/channels/<id>/messages", methods=["POST"])
@rate_limit(25, 60)
async def create_message(channel_id: str) -> tuple[Response, int]:
    data: dict[str, str] = g.data
    content: str = data.get("content", "")
    file_context_id: str | None = data.get("file_context_id")

    if not content and not file_context_id:
        raise FunctionError("INCORRECT_DATA", 400, None)

    async with AutoConnection(pool) as conn:
        channel = await chat.get_user_channel(g.user_id, channel_id, conn)

        for member in channel["members"]:
            await chat.add_channel_to_user_channels(
                member, channel_id, conn
            )

        message = await chat.create_message(
            channel_id, g.user_id, content, "plain", conn, file_context_id
        )

    return response(data={
        "message": message
    }), 200


@route(bp, "/user/<id>/messages", methods=["POST"])
@rate_limit(5, 60)
async def create_channel_and_message(id: str) -> tuple[Response, int]:
    data: dict[str, str] = g.data
    content: str = data.get("content", "")
    file_context_id: str | None = data.get("file_context_id")

    if not content and not file_context_id:
        raise FunctionError("INCORRECT_DATA", 400, None)

    async with AutoConnection(pool) as conn:
        channel_id = await chat.get_chat_channel_id(
            g.user_id, id, conn
        )
        if channel_id is None:
            channel_id = await chat.create_channel(
                [g.user_id, id], "direct", conn
            )

        await chat.add_channel_to_user_channels(
            g.user_id, channel_id, conn
        )
        await chat.add_channel_to_user_channels(
            id, channel_id, conn
        )

        channel = await chat.get_user_channel(g.user_id, channel_id, conn)

        message = await chat.create_message(
            channel_id, g.user_id, content, "plain", conn, file_context_id
        )

    return response(data={
        "channel": channel,
        "message": message
    }), 200


def load(app: Quart):
    app.register_blueprint(bp)
