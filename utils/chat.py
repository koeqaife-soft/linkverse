

import datetime
import typing as t
from utils.database import AutoConnection
import orjson
from utils.generation import generate_id
from core import FunctionError
from utils.storage import build_get_link


class UserChannel(t.TypedDict):
    user_id: str
    channel_id: str
    membership_id: str
    last_read_message_id: str
    last_read_at: datetime.datetime
    joined_at: datetime.datetime
    metadata: str | None  # JSONB
    type: t.Literal['direct', 'group']
    created_at: datetime.datetime
    members: list[str]


class Message(t.TypedDict):
    message_id: str
    channel_id: str
    user_id: str
    content: str
    content_type: t.Literal['plain', 'encrypted']
    file_context_id: str | None
    created_at: datetime.datetime
    edited_at: datetime.datetime | None
    media: list[str]


async def get_user_channels(
    user_id: str, conn: AutoConnection
) -> list[UserChannel]:
    db = await conn.create_conn()
    query = """
        SELECT *
        FROM user_channel_view
        WHERE user_id = $1
    """
    rows = await db.fetch(query, user_id)
    return [
        t.cast(UserChannel, dict(row))
        for row in rows
    ]


async def get_user_channel(
    user_id: str,
    channel_id: str,
    conn: AutoConnection
) -> UserChannel:
    db = await conn.create_conn()
    query = """
        SELECT *
        FROM user_channel_view
        WHERE user_id = $1 AND channel_id = $2
    """
    rows = await db.fetch(query, user_id, channel_id)
    return [
        t.cast(UserChannel, dict(row))
        for row in rows
    ]


async def create_channel(
    user_ids: list[str],
    type: t.Literal['direct', 'group'],
    conn: AutoConnection,
    metadata: dict[str, t.Any] = {}
) -> str:
    db = await conn.create_conn()
    async with db.transaction():
        query = """
            INSERT INTO channels (type, metadata, channel_id)
            VALUES ($1, $2, $3)
            RETURNING channel_id
        """
        new_channel_id = str(generate_id())
        row = await db.fetchrow(
            query, type, orjson.dumps(metadata).decode(), new_channel_id
        )
        channel_id = row['channel_id']

        values = [
            (channel_id, user_id, str(generate_id()))
            for user_id in user_ids
        ]

        query = """
            INSERT INTO channel_members (channel_id, user_id, membership_id)
            VALUES ($1, $2, $3)
        """
        await db.executemany(query, values)

    return channel_id


async def add_channel_to_user_channels(
    user_id: str,
    channel_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    async with db.transaction():
        membership_id = await ensure_membership(
            user_id, channel_id, conn
        )
        query = """
            INSERT INTO user_channels (user_id, channel_id, membership_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, channel_id) DO NOTHING
        """
        await db.execute(query, user_id, channel_id, membership_id)


async def ensure_membership(
    user_id: str,
    channel_id: str,
    conn: AutoConnection
) -> str:
    db = await conn.create_conn()
    membership_query = """
        SELECT membership_id FROM channel_members
        WHERE channel_id = $1 AND user_id = $2
    """
    row = await db.fetchrow(membership_query, channel_id, user_id)
    if row:
        return row['membership_id']
    else:
        raise FunctionError("FORBIDDEN", 403)


async def get_chat_channel_id(
    user_id: str,
    recipient_id: str,
    conn: AutoConnection
) -> str | None:
    db = await conn.create_conn()
    return await db.fetchval(
        """
        SELECT cm1.channel_id
        FROM channel_members cm1
        JOIN channel_members cm2
             ON cm1.channel_id = cm2.channel_id
        JOIN channels c
             ON c.channel_id = cm1.channel_id
        WHERE cm1.user_id = $1
              AND cm2.user_id = $2
              AND c.type = 'direct'
        LIMIT 1
        """,
        user_id, recipient_id
    )


def build_message_media(media: list | None) -> list:
    if media is None:
        return []

    new_media = []
    for file in media:
        new_media.append(build_get_link(file))

    return new_media


async def get_message(
    message_id: str,
    conn: AutoConnection
) -> Message | None:
    db = await conn.create_conn()
    query = """
        SELECT m.user_id, m.channel_id, m.content,
               m.content_type, m.file_context_id,
               m.message_id, m.created_at, m.edited_at,
               f.objects as media
        FROM messages m
        LEFT JOIN files f ON f.context_id = m.file_context_id
        WHERE message_id = $1
    """
    row = await db.fetchrow(query, message_id)
    if row:
        message = t.cast(Message, dict(row))
    else:
        raise FunctionError("MESSAGE_NOT_FOUND", 404)

    message['media'] = build_message_media(message.get('media'))

    return message


async def create_message(
    channel_id: str,
    user_id: str,
    content: str,
    content_type: t.Literal['plain', 'encrypted'],
    conn: AutoConnection,
    file_context_id: str | None = None
) -> Message:
    db = await conn.create_conn()

    async with db.transaction():
        new_message_id = str(generate_id())
        await db.execute(
            """
                INSERT INTO messages (
                    channel_id, user_id, content,
                    content_type, file_context_id, message_id
                )
                VALUES ($1, $2, $3, $4, $5, $6)
            """,
            channel_id,
            user_id,
            content,
            content_type,
            file_context_id,
            new_message_id
        )
        message = await get_message(new_message_id, conn)
        return message
