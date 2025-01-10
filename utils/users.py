from dataclasses import dataclass, asdict
from utils.generation import parse_id
from core import Status, FunctionError
from utils.database import AutoConnection
import typing as t


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
        return _dict

    def __dict__(self):
        return self.dict


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

    return Status(True, data=User(**dict(row)))


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


async def get_favorites(
    user_id: str, conn: AutoConnection,
    cursor: str | None = None,
    type: t.Literal["posts", "comments"] | None = None
) -> Status[list[str]]:
    db = await conn.create_conn()
    query = """
        SELECT post_id, comment_id, created_at
        FROM favorites WHERE user_id = $1
    """
    params = [user_id]

    if cursor:
        query += " AND created_at < $2"
        params.append(cursor)

    if type == "posts":
        query += " AND post_id IS NOT NULL AND comment_id IS NULL"
    elif type == "comments":
        query += " AND comment_id IS NOT NULL"

    query += " ORDER BY created_at DESC LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_FAVORITES", 200, None)

    favorites = [
        {
            "post_id": row["post_id"],
            "comment_id": row["comment_id"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]

    has_more = len(rows) > 20
    rows = rows[:20]

    last_row = rows[-1]

    next_cursor = last_row["created_at"].isoformat() if rows else None

    return Status(
        True,
        data={"favorites": favorites, "next_cursor": next_cursor,
              "has_more": has_more}
    )
