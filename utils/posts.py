from dataclasses import dataclass, asdict
import datetime
import re
import unicodedata
from core import FunctionError
from utils.generation import generate_id
import typing as t
from utils.database import AutoConnection, condition
from schemas import ListsDefault
from utils.storage import build_get_link


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
    media_type: str | None = None
    status: str | None = None
    is_deleted: bool | None = None
    ctags: list[str] | None = None

    @property
    def created_at_unix(self) -> float:
        if isinstance(self.created_at, int):
            return self.created_at
        return self.created_at.timestamp()

    @property
    def updated_at_unix(self) -> float:
        if isinstance(self.updated_at, int):
            return self.updated_at
        return self.updated_at.timestamp()

    @property
    def dict(self) -> dict:
        post_dict = asdict(self)
        post_dict['created_at'] = int(self.created_at_unix)
        post_dict['updated_at'] = int(self.updated_at_unix)
        return post_dict

    @staticmethod
    def from_dict(object: t.Dict) -> "Post":
        return Post(**dict(object))


class PostList(ListsDefault, t.TypedDict):
    posts: list[Post]


@dataclass
class Tag:
    tag_id: str
    name: str
    created_at: datetime.datetime
    posts_count: int

    @property
    def created_at_unix(self) -> float:
        if isinstance(self.created_at, int):
            return self.created_at
        return self.created_at.timestamp()

    @property
    def dict(self) -> dict:
        post_dict = asdict(self)
        post_dict['created_at'] = int(self.created_at_unix)
        return post_dict


def post_query(
    where: str = "",
    more_info: bool = False,
    popularity_score: bool = False
) -> str:
    query = f"""
        SELECT p.post_id, p.user_id, p.content, p.created_at, p.updated_at,
               p.likes_count, p.comments_count,
               p.dislikes_count, p.tags, m.objects as media,
               m.type as media_type
               {", p.popularity_score" if popularity_score else ""}
               {", p.status, p.is_deleted" if more_info else ""},
               COALESCE(
                   array_agg(t.name)
                   FILTER (WHERE t.tag_id IS NOT NULL),
                   '{{}}'
               ) AS ctags
        FROM posts p
        LEFT JOIN post_tags pt ON pt.post_id = p.post_id
        LEFT JOIN tags t ON t.tag_id = pt.tag_id
        LEFT JOIN files m ON m.context_id = p.file_context_id
        {where}
        GROUP BY p.post_id, m.objects, m.type
    """
    return query


def build_post_media(media: list) -> list:
    if media is None:
        return []

    new_media = []
    for file in media:
        new_media.append(build_get_link(file))

    return new_media


async def get_post(
    post_id: str,
    conn: AutoConnection,
    more_info: bool = False
) -> Post:
    db = await conn.create_conn()
    query = post_query(
        where="WHERE p.post_id = $1 AND p.is_deleted = FALSE",
        more_info=more_info
    )
    row = await db.fetchrow(query, post_id)

    if row is None:
        raise FunctionError("POST_DOES_NOT_EXIST", 404, None)

    data = dict(row)
    data["media"] = build_post_media(data["media"])
    return Post.from_dict(data)


def normalize_tag(tag: str) -> str:
    tag = tag.strip().lower()
    tag = unicodedata.normalize("NFKD", tag)
    tag = re.sub(r"[^\w\s-]", "", tag)
    tag = re.sub(r"[\s]+", "-", tag)
    tag = tag[:50]
    return tag


async def create_post(
    user_id: str, content: str,
    conn: AutoConnection,
    tags: list[str] = [],
    file_context_id: str | None = None,
    ctags: list[str] = []
) -> dict | None:
    db = await conn.create_conn()
    post_id = str(generate_id())
    ctags = list(set([normalize_tag(tag) for tag in ctags if tag]))
    await conn.start_transaction()
    await db.execute(
        """
        INSERT INTO posts
        (post_id, user_id, content, tags, file_context_id)

        VALUES ($1, $2, $3, $4, $5)
        """, post_id, user_id, content, tags, file_context_id
    )

    if ctags:
        await db.executemany(
            """
            INSERT INTO tags (name, tag_id)
            VALUES ($1, $2)
            ON CONFLICT (name) DO NOTHING
            """,
            [(tag, str(generate_id())) for tag in ctags]
        )
        await db.executemany(
            """
            INSERT INTO post_tags (post_id, tag_id)
            SELECT $1, tag_id FROM tags WHERE name = $2
            ON CONFLICT DO NOTHING
            """,
            [(post_id, tag) for tag in ctags]
        )

    created_post = await get_post(post_id, conn, more_info=False)

    return created_post.dict


async def delete_post(
    post_id: str, conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    await conn.start_transaction()
    await db.execute(
        """
        UPDATE posts
        SET is_deleted = $1
        WHERE post_id = $2
        """, True, post_id
    )


async def update_post(
    post_id: str, content: str | None,
    tags: list[str] | None,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()
    if content is None and tags is None:
        raise ValueError("All arguments is None!")
    _parameters = []
    _query = []
    _keys = {
        "content": content,
        "tags": tags
    }
    for key, value in _keys.items():
        if value is not None:
            _parameters.append(value)
            _query.append(f"{key} = ${len(_parameters)}")

    await conn.start_transaction()
    await db.execute(
        f"""
        UPDATE posts
        SET {", ".join(_query)}
        WHERE post_id = ${len(_parameters)+1}
        """, *_parameters, post_id
    )


async def add_reaction(
    user_id: str, is_like: bool,
    post_id: str | None,
    comment_id: str | None,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    result = await db.fetchval(
        f"""
        SELECT is_like FROM reactions
        WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
        """, user_id, post_id, *_params
    )
    if result == is_like:
        return

    await conn.start_transaction()
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


async def get_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    conn: AutoConnection
) -> None | bool:
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
        return result
    else:
        return None


async def rem_reaction(
    user_id: str,
    post_id: str,
    comment_id: str | None,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    _condition, _params = condition(comment_id, 3)

    await conn.start_transaction()
    await db.execute(
        f"""
        DELETE FROM reactions
        WHERE user_id = $1 AND post_id = $2 AND comment_id {_condition}
        """, user_id, post_id, *_params
    )


async def get_user_posts(
    user_id: str,
    cursor: str | None,
    conn: AutoConnection,
    sort: t.Literal["popular", "new", "old"] | None = None
) -> PostList:
    sort = sort or "new"
    db = await conn.create_conn()
    query = post_query(
        where="WHERE p.user_id = $1 AND p.is_deleted = FALSE",
        popularity_score=True
    )
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
                    (p.popularity_score) < $2 OR
                    ((p.popularity_score) = $2 AND p.post_id < $3)
                )
            """
            params.extend([popularity_score, post_id])
        elif sort == "new":
            query += " AND p.post_id < $2"
            params.append(post_id)
        elif sort == "old":
            query += " AND p.post_id > $2"
            params.append(post_id)

    if sort == "popular":
        query += " ORDER BY p.popularity_score DESC, p.post_id::bigint DESC"
    elif sort == "new":
        query += " ORDER BY p.post_id::bigint DESC"
    elif sort == "old":
        query += " ORDER BY p.post_id::bigint ASC"

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

    for post in posts:
        post.media = build_post_media(post.media)

    return {"posts": posts, "next_cursor": next_cursor, "has_more": has_more}


async def get_fav_and_reaction(
    user_id: str,
    conn: AutoConnection,
    post_id: str,
    comment_id: str | None = None
) -> tuple[bool | None, bool | None]:
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

    return result


async def get_tag(
    tag_name: str,
    conn: AutoConnection
) -> Tag:
    db = await conn.create_conn()
    row = await db.fetchrow(
        """
        SELECT tag_id, name, created_at, posts_count
        FROM tags
        WHERE name = $1
        """, tag_name
    )
    if row is None:
        raise FunctionError("TAG_DOES_NOT_EXIST", 404, None)
    return Tag(**dict(row))
