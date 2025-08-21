from dataclasses import dataclass, asdict
import datetime
from core import Status, FunctionError
from utils.generation import generate_id
import typing as t
from utils.database import AutoConnection, condition
from schemas import ListsDefault


@dataclass
class Post:
    post_id: str
    user_id: str
    content: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    likes_count: int
    dislikes_count: int
    comments_count: int
    tags: list[str]
    media: list[str]
    status: str | None = None
    is_deleted: bool | None = None

    @property
    def created_at_unix(self) -> float:
        return self.created_at.timestamp()

    @property
    def updated_at_unix(self) -> float:
        return self.updated_at.timestamp()

    @property
    def dict(self) -> dict:
        post_dict = asdict(self)
        post_dict['created_at'] = int(self.created_at_unix)
        post_dict['updated_at'] = int(self.updated_at_unix)
        return post_dict

    def __dict__(self):
        return self.dict

    @staticmethod
    def from_dict(object: t.Dict) -> "Post":
        return Post(**dict(object))


class PostList(t.TypedDict, ListsDefault):
    posts: list[Post]


async def get_post(
    post_id: str, conn: AutoConnection,
    more_info: bool = False
) -> Status[Post]:
    db = await conn.create_conn()
    query = f"""
        SELECT post_id, user_id, content, created_at, updated_at,
               likes_count, comments_count, dislikes_count, tags, media
               {", status, is_deleted" if more_info else ""}
        FROM posts
        WHERE post_id = $1 AND is_deleted = FALSE
    """
    row = await db.fetchrow(query, post_id)

    if row is None:
        raise FunctionError("POST_DOES_NOT_EXIST", 404, None)

    return Status(True, data=Post.from_dict(row))


async def create_post(
    user_id: str, content: str,
    conn: AutoConnection,
    tags: list[str] = [],
    media: list[str] = []
) -> Status[dict | None]:
    db = await conn.create_conn()
    post_id = str(generate_id())
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO posts (post_id, user_id, content, tags, media)
            VALUES ($1, $2, $3, $4, $5)
            """, post_id, user_id, content, tags, media
        )
        created_post = await db.fetchrow(
            """
            SELECT post_id, user_id, content, created_at, updated_at,
                   likes_count, comments_count, tags, media, status,
                   is_deleted, dislikes_count
            FROM posts WHERE post_id = $1
            """, post_id
        )

    return Status(
        True,
        data=(
            Post.from_dict(created_post).dict
            if created_post else None
        )
    )


async def delete_post(
    post_id: str, conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE posts
            SET is_deleted = $1
            WHERE post_id = $2
            """, True, post_id
        )

    return Status(True)


async def update_post(
    post_id: str, content: str | None,
    tags: list[str] | None, media: list[str] | None,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    if content is None and tags is None and media is None:
        raise ValueError("All arguments is None!")
    _parameters = []
    _query = []
    _keys = {
        "content": content,
        "tags": tags,
        "media": media
    }
    for key, value in _keys.items():
        if value is not None:
            _parameters.append(value)
            _query.append(f"{key} = ${len(_parameters)}")

    async with db.transaction():
        await db.execute(
            f"""
            UPDATE posts
            SET {", ".join(_query)}
            WHERE post_id = ${len(_parameters)+1}
            """, *_parameters, post_id
        )

    return Status(True)


async def add_reaction(
    user_id: str, is_like: bool,
    post_id: str | None,
    comment_id: str | None,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    result = await db.fetchval(
        f"""
        SELECT is_like FROM reactions
        WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
        """, user_id, post_id, *_params
    )
    if result == is_like:
        return Status(True)

    async with db.transaction():
        if result is None:
            await db.execute(
                """
                INSERT INTO reactions (user_id, post_id, comment_id, is_like)
                VALUES ($1, $2, $3, $4)
                """, user_id, post_id, comment_id, is_like
            )
        else:
            _condition, _params = condition(comment_id, 4)

            await db.execute(
                f"""
                UPDATE reactions
                SET is_like = $1
                WHERE user_id = $2 AND post_id = $3
                AND comment_id {_condition}
                """, is_like, user_id, post_id, *_params
            )
    return Status(True)


async def get_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    conn: AutoConnection
) -> Status[None | bool]:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    result = await db.fetchval(
        f"""
        SELECT is_like FROM reactions
        WHERE user_id = $1 AND post_id = $2
        AND comment_id {_condition}
        """, user_id, post_id, *_params
    )
    if result is not None:
        return Status(True, data=result)
    else:
        return Status(True)


async def rem_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    async with db.transaction():
        await db.execute(
            f"""
            DELETE FROM reactions
            WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
            """, user_id, post_id, *_params
        )
    return Status(True)


async def get_user_posts(
    user_id: str,
    cursor: str | None,
    conn: AutoConnection,
    sort: t.Literal["popular", "new", "old"] | None = None
) -> Status[PostList]:
    sort = sort or "new"
    db = await conn.create_conn()
    query = """
        SELECT post_id, user_id, content, created_at, updated_at,
               likes_count, comments_count, tags, media, status,
               is_deleted, dislikes_count,
               popularity_score
        FROM posts WHERE user_id = $1 AND is_deleted = FALSE
    """
    params: list[t.Any] = [user_id]

    if cursor:
        try:
            _popularity_score, post_id = cursor.split(",")
            popularity_score = int(_popularity_score)
        except ValueError:
            raise FunctionError("INVALID_CURSOR", 400, None)

        if sort == "popular":
            query += """
                AND (
                    (popularity_score) < $2 OR
                    ((popularity_score) = $2 AND post_id < $3)
                )
            """
            params.extend([popularity_score, post_id])
        elif sort == "new":
            query += " AND post_id < $2"
            params.append(post_id)
        elif sort == "old":
            query += " AND post_id > $2"
            params.append(post_id)

    if sort == "popular":
        query += " ORDER BY popularity_score DESC, post_id::bigint DESC"
    elif sort == "new":
        query += " ORDER BY post_id::bigint DESC"
    elif sort == "old":
        query += " ORDER BY post_id::bigint ASC"

    query += " LIMIT 21"

    rows = await db.fetch(query, *params)
    if not rows:
        raise FunctionError("NO_MORE_POSTS", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    last_row = rows[-1]
    next_cursor = (
        f"{last_row['popularity_score']},{last_row['post_id']}"
    )
    posts = [
        Post(
            **{k: v for k, v in row.items()
               if k != 'popularity_score'}
        )
        for row in rows
    ]
    return Status(
        success=True,
        data={"posts": posts, "next_cursor": next_cursor, "has_more": has_more}
    )


async def get_fav_and_reaction(
    user_id: str,
    conn: AutoConnection,
    post_id: str,
    comment_id: str | None = None
) -> Status[tuple[bool | None, bool | None]]:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    row = await db.fetchrow(
        f"""
        SELECT EXISTS (
            SELECT 1
            FROM favorites
            WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
        ) AS is_favorite, (
            SELECT is_like
            FROM reactions
            WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
        ) AS reaction
        """,
        user_id, post_id, *_params
    )

    result = (row["is_favorite"] if row else None,
              row["reaction"] if row else None)

    return Status(True, data=result)
