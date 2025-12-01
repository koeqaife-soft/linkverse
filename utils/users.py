from dataclasses import dataclass, asdict
from datetime import datetime
from utils.generation import parse_id
from core import FunctionError
from utils.database import AutoConnection
import typing as t
from schemas import FollowedList, FavoriteList, ReactionList
from schemas import FollowedItem, FavoriteItem, ReactionItem
import utils.storage as storage
from enum import IntFlag, auto


@dataclass
class User:
    user_id: str
    username: str
    role_id: int = 0
    following_count: int | None = None
    followers_count: int | None = None
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
    def dict(self) -> dict[str, t.Any]:
        _dict = asdict(self)
        _dict["created_at"] = self.created_at
        return {key: value for key, value in _dict.items()
                if value is not None}

    @staticmethod
    def from_dict(object: t.Dict) -> "User":
        return User(**dict(object))


class Permission(IntFlag):
    NONE = 0
    MODERATE_POSTS = auto()
    MODERATE_COMMENTS = auto()
    MODERATE_PROFILES = auto()
    BAN_USERS = auto()
    RED_BUTTON = auto()
    REVIEW_APPELLATIONS = auto()
    ADMIN_PANEL = auto()
    ALL = ~0


ROLE_USER = Permission.NONE
ROLE_TRUSTED = Permission.RED_BUTTON
ROLE_MODERATOR = (
    Permission.MODERATE_POSTS |
    Permission.MODERATE_COMMENTS |
    Permission.MODERATE_PROFILES
)
ROLE_ADMIN = (
    ROLE_TRUSTED | ROLE_MODERATOR |
    Permission.BAN_USERS |
    Permission.ADMIN_PANEL
)
ROLE_OWNER = Permission.ALL
ROLES = {
    0: ROLE_USER,
    1: ROLE_TRUSTED,
    2: ROLE_TRUSTED | ROLE_MODERATOR,
    3: ROLE_MODERATOR,
    4: ROLE_ADMIN,
    999: ROLE_OWNER
}


def permissions_to_list(perms: Permission) -> list[str]:
    return [
        perm.name
        for perm in Permission
        if perm in perms
        and perm is not Permission.ALL
        and perm.name is not None
    ]


async def get_user(
    user_id: str, conn: AutoConnection,
    minimize_info: bool = False
) -> User:
    db = await conn.create_conn()
    query = f"""
        SELECT u.user_id, u.username, p.display_name, u.role_id,
               ac.objects[1] as avatar_url
               {", bc.objects[1] as banner_url, p.bio, p.badges, p.languages"
                ", u.following_count, u.followers_count"
                if not minimize_info else ""}
        FROM users u
        LEFT JOIN user_profiles p ON u.user_id = p.user_id
        LEFT JOIN files ac ON ac.context_id = p.avatar_context_id
        {"LEFT JOIN files bc ON bc.context_id = p.banner_context_id"
         if not minimize_info else ""}
        WHERE u.user_id = $1;
    """
    row = await db.fetchrow(query, user_id)

    if row is None:
        raise FunctionError("USER_DOES_NOT_EXIST", 404, None)

    _dict = dict(row)
    for name in ("avatar_url", "banner_url"):
        if _dict.get(name) and "://" not in str(_dict[name]):
            _dict[name] = f"{storage.PUBLIC_PATH}/{_dict[name]}"

    return User.from_dict(_dict)


async def check_permission(
    user_id: str,
    perm: Permission,
    conn: AutoConnection
) -> bool:
    db = await conn.create_conn()
    value = await db.fetchval(
        """
        SELECT role_id
        FROM users
        WHERE user_id = $1
        """, user_id
    )

    if value not in ROLES:
        return False

    return bool(ROLES[value] & perm)


async def update_user(
    user_id: str, values: dict[str, str],
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    allowed_values = {
        "display_name",
        "avatar_context_id",
        "banner_context_id",
        "bio",
        "languages"
    }

    new_values = {
        k: v for k, v in values.items()
        if k in allowed_values
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
    await conn.start_transaction()
    await db.execute(
        query, user_id, *new_values.values()
    )


async def change_username(
    user_id: str, username: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        UPDATE users
        SET username = $1
        WHERE user_id = $2
        """, username, user_id
    )


async def add_badge(
    user_id: str, badge: int,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    query = """
        INSERT INTO user_profiles (user_id, badges)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET badges = array_append(user_profiles.badges, $2)
    """
    await conn.start_transaction()
    await db.execute(
        query, user_id, badge
    )


async def rem_badge(
    user_id: str, badge: int,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    query = """
        UPDATE user_profiles
        SET badges = array_remove(badges, $2)
        WHERE user_id = $1
    """
    await conn.start_transaction()
    await db.execute(
        query, user_id, badge
    )


async def clear_badges(
    user_id: str, conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        UPDATE user_profiles
        SET badges = NULL
        WHERE user_id = $1
        """, user_id
    )


async def add_to_favorites(
    user_id: str,
    conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
            INSERT INTO favorites (user_id, comment_id, post_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (post_id, comment_id, user_id) DO NOTHING
        """, user_id, comment_id, post_id
    )


async def rem_from_favorites(
    user_id: str,
    conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> None:
    key = "comment_id" if comment_id else "post_id"
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        f"""
            DELETE FROM favorites
            WHERE user_id = $1 AND {key} = $2
        """, user_id, comment_id or post_id
    )


async def is_favorite(
    user_id: str, conn: AutoConnection,
    post_id: str | None = None,
    comment_id: str | None = None
) -> bool:
    key = "comment_id" if comment_id else "post_id"
    db = await conn.create_conn()
    row = await db.fetchrow(
        f"""
            SELECT 1
            FROM favorites
            WHERE user_id = $1 AND {key} = $2
        """, user_id, comment_id or post_id
    )

    return row is not None


async def follow(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        INSERT INTO followed (user_id, followed_to)
        VALUES ($1, $2)
        ON CONFLICT (user_id, followed_to) DO NOTHING
        """, user_id, target_id
    )


async def unfollow(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        DELETE FROM followed
        WHERE user_id = $1 AND followed_to = $2
        """, user_id, target_id
    )


async def is_followed(
    user_id: str, target_id: str,
    conn: AutoConnection
) -> bool:
    db = await conn.create_conn()
    row = await db.fetchrow(
        """
        SELECT 1
        FROM followed
        WHERE user_id = $1 AND followed_to = $2
        """, user_id, target_id
    )

    return row is not None


async def get_followed(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None
) -> FollowedList:
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

    return {
        "followed": followed,
        "next_cursor": next_cursor,
        "has_more": has_more
    }


async def get_favorites(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None,
    type: t.Literal["posts", "comments"] | None = None
) -> FavoriteList:
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

    return {
        "favorites": favorites,
        "next_cursor": next_cursor,
        "has_more": has_more
    }


async def get_reactions(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None,
    type: t.Literal["posts", "comments"] | None = None,
    is_like: bool | None = None
) -> ReactionList:
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

    return {
        "reactions": reactions,
        "next_cursor": next_cursor,
        "has_more": has_more
    }
