from dataclasses import dataclass, asdict
import datetime
from core import Status
from utils.generation import generate_id
from _types import connection_type
import typing as t


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
    status: str
    is_deleted: bool

    @property
    def created_at_unix(self) -> float:
        return self.created_at.timestamp()

    @property
    def updated_at_unix(self) -> float:
        return self.updated_at.timestamp()

    def to_dict(self) -> dict:
        post_dict = asdict(self)
        post_dict['created_at_unix'] = self.created_at_unix
        post_dict['updated_at_unix'] = self.updated_at_unix
        return post_dict


@dataclass
class Comment:
    comment_id: str
    post_id: str
    user_id: str
    content: str
    parent_comment_id: str | None
    likes_count: int
    dislikes_count: int

    def to_dict(self) -> dict:
        return asdict(self)


async def get_post(
    post_id: str, db: connection_type
) -> Status[Post | None]:
    query = """
        SELECT post_id, user_id, content, created_at, updated_at,
               likes_count, comments_count, tags, media, status, is_deleted,
               dislikes_count
        FROM posts
        WHERE post_id = $1 AND is_deleted = FALSE
    """
    row = await db.fetchrow(query, post_id)

    if row is None:
        return Status(False, message="POST_DOES_NOT_EXIST")

    return Status(True, data=Post(**dict(row)))


async def create_post(
    user_id: str, content: str,
    db: connection_type,
    tags: list[str] = [],
    media: list[str] = []
) -> Status[dict | None]:
    post_id = str(await generate_id())
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
            Post(**dict(created_post)).to_dict()
            if created_post else None
        )
    )


async def delete_post(
    post_id: str, db: connection_type
) -> Status[None]:
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
    db: connection_type
) -> Status[None]:
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
    db: connection_type
) -> Status[None]:
    key = "post_id" if post_id is not None else "comment_id"
    _value = post_id or comment_id
    result = await db.fetchval(
        f"""
        SELECT is_like FROM reactions
        WHERE user_id = $1 AND {key} = $2
        """, user_id, _value
    )
    if result == is_like:
        return Status(True)

    async with db.transaction():
        await db.execute(
            f"""
            INSERT INTO reactions (user_id, {key}, is_like)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, {key})
            DO UPDATE SET is_like = excluded.is_like
            """, user_id, _value, is_like
        )
    return Status(True)


async def get_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    db: connection_type
) -> Status[None | bool]:
    key = "post_id" if post_id is not None else "comment_id"
    _value = post_id or comment_id

    result = await db.fetchval(
        f"""
        SELECT is_like FROM reactions
        WHERE user_id = $1 AND {key} = $2
        """, user_id, _value
    )
    if result is not None:
        return Status(True, data=result)
    else:
        return Status(True)


async def rem_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    db: connection_type
) -> Status[None]:
    key = "post_id" if post_id is not None else "comment_id"
    _value = post_id or comment_id

    async with db.transaction():
        await db.execute(
            f"""
            DELETE FROM reactions
            WHERE user_id = $1 AND {key} = $2
            """, user_id, _value
        )
    return Status(True)


async def create_comment(
    user_id: str, post_id: str, content: str,
    db: connection_type
) -> Status[Comment | None]:
    comment_id = str(await generate_id())
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO comments (comment_id, post_id, user_id, content)
            VALUES ($1, $2, $3, $4)
            """, comment_id, post_id, user_id, content
        )
        comment = await db.fetchrow(
            """
                SELECT comment_id, parent_comment_id, post_id, user_id,
                       content, likes_count, dislikes_count
                FROM comments
                WHERE post_id = $1 AND comment_id = $2
            """, post_id, comment_id
        )

    return Status(True, data=Comment(**dict(comment)))


async def get_comment(
    post_id: str, comment_id: str,
    db: connection_type
) -> Status[Comment | None]:
    query = """
        SELECT comment_id, parent_comment_id, post_id, user_id, content,
               likes_count, dislikes_count
        FROM comments
        WHERE post_id = $1 AND comment_id = $2
    """
    row = await db.fetchrow(query, post_id, comment_id)

    if row is None:
        return Status(False, message="COMMENT_DOES_NOT_EXIST")

    return Status(True, data=Comment(**dict(row)))


async def get_comments(
    post_id: str,
    cursor: str | None,
    user_id: str,
    db: connection_type
) -> Status[dict[
            t.Literal["comments"] | t.Literal["next_cursor"],
            list[Comment] | str] | None]:
    query = """
        SELECT comment_id, parent_comment_id, post_id, user_id, content,
               likes_count, dislikes_count,
               (likes_count - dislikes_count) AS popularity_score,
               CASE WHEN user_id = $2 THEN 1 ELSE 0 END AS is_user_comment
        FROM comments
        WHERE post_id = $1
    """
    params: list[t.Any] = [post_id, user_id]

    if cursor:
        try:
            _popularity_score, comment_id = cursor.split(",")
            popularity_score = int(_popularity_score)
        except ValueError:
            return Status(False, message="INVALID_CURSOR")

        query += """
            AND (
                (likes_count - dislikes_count) > $3 OR
                ((likes_count - dislikes_count) = $3 AND comment_id < $4)
            )
        """
        params.extend([popularity_score, comment_id])

    query += """
        ORDER BY is_user_comment DESC, popularity_score DESC, comment_id DESC
        LIMIT 21
    """

    rows = await db.fetch(query, *params)
    if not rows:
        return Status(False, message="NO_MORE_COMMENTS")

    has_more = len(rows) > 20
    rows = rows[:20]

    last_row = rows[-1]
    next_cursor = f"{last_row['popularity_score']},{last_row['comment_id']}"

    comments = [
        Comment(
            **{k: v for k, v in row.items()
               if k not in ['popularity_score', 'is_user_comment']}
        )
        for row in rows
    ]
    return Status(
        success=True,
        data={"comments": comments, "next_cursor": next_cursor,
              "has_more": has_more}
    )
