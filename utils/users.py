from dataclasses import dataclass, asdict
from datetime import datetime
from utils.generation import parse_id, snowflake
from core import Status, FunctionError
from utils.database import AutoConnection
import typing as t
from schemas import FollowedList, FavoriteList, ReactionList
from schemas import FollowedItem, FavoriteItem, ReactionItem
from schemas import NotificationType, NotificationList, Notification


@dataclass
class User:
    user_id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    bio: str | None = None
    badges: list[str] | None = None
    languages: list[str] | None = None

    @property
    def created_at(self):
        try:
            return self._created_at
        except AttributeError:
            self._created_at = int(parse_id(self.user_id)[0])
            return self._created_at

    @property
    def dict(self) -> dict:
        _dict = asdict(self)
        _dict["created_at"] = self.created_at
        return {key: value for key, value in _dict.items()
                if value is not None}

    def __dict__(self):
        return self.dict

    @staticmethod
    def from_dict(object: t.Dict) -> "User":
        return User(**dict(object))


async def get_user(
    user_id: str, conn: AutoConnection,
    minimize_info: bool = False
) -> Status[User]:
    db = await conn.create_conn()
    query = f"""
        SELECT u.user_id, u.username, p.display_name, p.avatar_url
               {",p.banner_url, p.bio, p.badges, p.languages"
                if not minimize_info else ""}
        FROM users u
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        WHERE u.user_id = $1;
    """
    row = await db.fetchrow(query, user_id)

    if row is None:
        raise FunctionError("USER_DOES_NOT_EXIST", 404, None)

    return Status(True, data=User.from_dict(row))


async def update_user(
    user_id: str, values: dict[str, str],
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    allowed_values = {"display_name", "avatar_url", "banner_url",
                      "bio", "languages"}

    new_values = {
        k: v for k, v in values.items()
        if k in allowed_values and v is not None
    }

    if not new_values:
        raise FunctionError("NO_DATA", 404, None)

    columns = ', '.join(new_values.keys())
    placeholders = ', '.join(f'${i+2}' for i in range(len(new_values)))
    update_clause = ', '.join(f"{k} = EXCLUDED.{k}" for k in new_values)

    query = f"""
        INSERT INTO user_profiles (user_id, {columns})
        VALUES ($1, {placeholders})
        ON CONFLICT (user_id)
        DO UPDATE SET {update_clause}
    """
    async with db.transaction():
        await db.execute(
            query, user_id, *new_values.values()
        )
    return Status(True)


async def change_username(
    user_id: str, username: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE users
            SET username = $1
            WHERE user_id = $2
            """, username, user_id
        )
    return Status(True)


async def add_badge(
    user_id: str, badge: int,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    query = """
        INSERT INTO user_profiles (user_id, badges)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET badges = array_append(user_profiles.badges, $2)
    """
    async with db.transaction():
        await db.execute(
            query, user_id, badge
        )
    return Status(True)


async def rem_badge(
    user_id: str, badge: int,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    query = """
        UPDATE user_profiles
        SET badges = array_remove(badges, $2)
        WHERE user_id = $1
    """
    async with db.transaction():
        await db.execute(
            query, user_id, badge
        )
    return Status(True)


async def clear_badges(
    user_id: str, conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE user_profiles
            SET badges = NULL
            WHERE user_id = $1
            """, user_id
        )
    return Status(True)


async def add_to_favorites(
    user_id: str,
    conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
                INSERT INTO favorites (user_id, comment_id, post_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (post_id, comment_id, user_id) DO NOTHING
            """, user_id, comment_id, post_id
        )

    return Status(True)


async def rem_from_favorites(
    user_id: str,
    conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> Status[None]:
    key = "comment_id" if comment_id else "post_id"
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            f"""
                DELETE FROM favorites
                WHERE user_id = $1 AND {key} = $2
            """, user_id, comment_id or post_id
        )

    return Status(True)


async def is_favorite(
    user_id: str, conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> Status[bool]:
    key = "comment_id" if comment_id else "post_id"
    db = await conn.create_conn()
    row = await db.fetchrow(
        f"""
            SELECT 1
            FROM favorites
            WHERE user_id = $1 AND {key} = $2
        """, user_id, comment_id or post_id
    )

    return Status(True, data=row is not None)


async def follow(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO followed (user_id, followed_to)
            VALUES ($1, $2)
            ON CONFLICT (user_id, followed_to) DO NOTHING
            """, user_id, target_id
        )

    return Status(True)


async def unfollow(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            DELETE FROM followed
            WHERE user_id = $1 AND followed_to = $2
            """, user_id, target_id
        )

    return Status(True)


async def is_followed(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> Status[bool]:
    db = await conn.create_conn()
    row = await db.fetchrow(
        """
        SELECT 1
        FROM followed
        WHERE user_id = $1 AND followed_to = $2
        """, user_id, target_id
    )

    return Status(True, data=row is not None)


async def get_followed(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None
) -> Status[FollowedList]:
    db = await conn.create_conn()
    query = """
        SELECT followed_to, created_at
        FROM followed WHERE user_id = $1
    """
    params: list[t.Any] = [user_id]

    if cursor:
        query += (
            " AND (created_at < $2 OR (created_at = $2 and followed_to < $3))"
        )
        post_id, _date = cursor.split("_")
        date = datetime.fromisoformat(_date.replace('Z', '+00:00'))
        params.extend([date, post_id])

    query += " ORDER BY created_at DESC LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_FOLLOWED", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    followed = [
        FollowedItem({
            "followed_to": row["followed_to"],
            "created_at": row["created_at"]
        })
        for row in rows
    ]

    last_row = rows[-1]

    next_cursor = (
        f"{last_row["followed_to"]}_{last_row["created_at"].isoformat()}"
        if rows else None
    )

    return Status(
        True,
        data={
            "followed": followed,
            "next_cursor": next_cursor,
            "has_more": has_more
        }
    )


async def get_favorites(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None,
    type: t.Literal["posts", "comments"] | None = None
) -> Status[FavoriteList]:
    db = await conn.create_conn()
    query = """
        SELECT post_id, comment_id, created_at
        FROM favorites WHERE user_id = $1
    """
    params: list[t.Any] = [user_id]

    if cursor:
        query += " AND (created_at < $2 OR (created_at = $2 AND post_id < $3))"
        post_id, _date = cursor.split("_")
        date = datetime.fromisoformat(_date.replace('Z', '+00:00'))
        params.extend([date, post_id])

    if type == "posts":
        query += " AND comment_id IS NULL"
    elif type == "comments":
        query += " AND comment_id IS NOT NULL"

    query += " ORDER BY created_at DESC LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_FAVORITES", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    favorites = [
        FavoriteItem({
            "post_id": row["post_id"],
            "comment_id": row["comment_id"],
            "created_at": row["created_at"].isoformat(),
        })
        for row in rows
    ]

    last_row = rows[-1]

    next_cursor = (
        f"{last_row["post_id"]}_{last_row["created_at"].isoformat()}"
        if rows else None
    )

    return Status(
        True,
        data={
            "favorites": favorites,
            "next_cursor": next_cursor,
            "has_more": has_more
        }
    )


async def get_reactions(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None,
    type: t.Literal["posts", "comments"] | None = None,
    is_like: bool | None = None
) -> Status[ReactionList]:
    db = await conn.create_conn()
    query = """
        SELECT post_id, comment_id, created_at, is_like
        FROM reactions WHERE user_id = $1
    """
    params: list[t.Any] = [user_id]

    if cursor:
        query += " AND (created_at < $2 OR (created_at = $2 AND post_id < $3))"
        post_id, _date = cursor.split("_")
        date = datetime.fromisoformat(_date.replace('Z', '+00:00'))
        params.extend([date, post_id])

    if type == "posts":
        query += " AND comment_id IS NULL"
    elif type == "comments":
        query += " AND comment_id IS NOT NULL"

    if is_like is not None:
        query += f" AND is_like = ${len(params) + 1}"
        params.append(is_like)

    query += " ORDER BY created_at DESC LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_REACTIONS", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    reactions = [
        ReactionItem({
            "post_id": row["post_id"],
            "comment_id": row["comment_id"],
            "created_at": row["created_at"].isoformat(),
            "is_like": row["is_like"]
        })
        for row in rows
    ]

    last_row = rows[-1]

    next_cursor = (
        f"{last_row["post_id"]}_{last_row["created_at"].isoformat()}"
        if rows else None
    )

    return Status(
        True,
        data={
            "reactions": reactions,
            "next_cursor": next_cursor,
            "has_more": has_more
        }
    )


async def create_notification(
    user_id: str,
    from_id: str,
    type: NotificationType | str,
    conn: AutoConnection,
    message: str | None = None,
    linked_type: str | None = None,
    linked_id: str | None = None,
    second_linked_id: str | None = None
) -> Status[Notification]:
    if user_id == from_id:
        return Status(True)

    db = await conn.create_conn()

    notification_id = str(snowflake.generate())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO user_notifications (
                id, user_id, type, message, from_id,
                linked_type, linked_id, second_linked_id
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            """,
            notification_id, user_id, type, message, from_id,
            linked_type, linked_id, second_linked_id
        )

    notification = Notification({
        "id": notification_id,
        "from_id": from_id,
        "message": message,
        "type": type,
        "linked_type": linked_type,
        "linked_id": linked_id,
        "second_linked_id": second_linked_id
    })

    return Status(True, data=notification)


async def get_notifications(
    user_id: str,
    conn: AutoConnection,
    cursor: str | None = None
) -> Status[NotificationList]:
    db = await conn.create_conn()
    query = """
        SELECT type, message, from_id,
               linked_type, linked_id, second_linked_id
        FROM reactions WHERE user_id = $1
    """
    params: list[t.Any] = [user_id]

    if cursor:
        query += " AND id < $2"
        params.append(cursor)

    query += " ORDER BY id DESC LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_NOTIFS", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    notifications = [
        Notification({
            "id": row["id"],
            "type": row["type"],
            "message": row["message"],
            "from_id": row["from_id"],
            "linked_type": row["linked_type"],
            "linked_id": row["linked_id"],
            "second_linked_id": row["second_linked_id"]
        })
        for row in rows
    ]

    last_row = rows[-1]

    next_cursor = last_row["id"]

    return Status(
        True,
        data={
            "notifications": notifications,
            "next_cursor": next_cursor,
            "has_more": has_more
        }
    )
