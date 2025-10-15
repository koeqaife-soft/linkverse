

import datetime
import typing as t
from utils.database import AutoConnection
import orjson
from utils.generation import generate_id
from core import FunctionError


class UserChannel(t.TypedDict):
    user_id: str
    channel_id: str
    membership_id: str
    last_read_message_id: str
    last_read_at: datetime.datetime
    joined_at: datetime.datetime
    metadata: str | None  # JSONB
    type: t.Literal['private', 'group']
    created_at: datetime.datetime


class Message(t.TypedDict):
    message_id: str
    channel_id: str
    user_id: str
    content: str
    content_type: t.Literal['plain', 'encrypted']
    file_context_id: str | None
    created_at: datetime.datetime
    edited_at: datetime.datetime | None


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


async def create_channel(
    user_ids: list[str],
    type: t.Literal['private', 'group'],
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
            query, type, orjson.dumps(metadata), new_channel_id
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
