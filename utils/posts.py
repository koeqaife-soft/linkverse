from dataclasses import dataclass, asdict
import datetime
from core import Status
from utils.generation import generate_id, Action
from _types import connection_type


@dataclass
class Post:
    post_id: int
    user_id: int
    content: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    likes_count: int
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


async def get_post(
    where: dict[str, int | str | bool],
    db: connection_type
) -> Status[Post | None]:
    if not where:
        raise ValueError("The 'where' dictionary must not be empty")

    conditions: list[str] = []
    values = []
    for key, value in where.items():
        conditions.append(f"{key} = ${len(conditions) + 1}")
        values.append(value)

    query = f"""
        SELECT post_id, user_id, content, created_at, updated_at,
               likes_count, comments_count, tags, media, status, is_deleted
        FROM posts
        WHERE {' AND '.join(conditions)}
    """
    row = await db.fetchrow(query, *values)

    if row is None:
        return Status(False, message="POST_DOES_NOT_EXIST")

    return Status(True, data=Post(**dict(row)))


async def create_post(
    user_id: int, content: str,
    db: connection_type,
    tags: list[str] = [],
    media: list[str] = []
) -> Status[dict | None]:
    post_id = await generate_id(Action.CREATE_POST)
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO posts (post_id, user_id, content, tags, media)
            VALUES ($1, $2, $3, $4, $5)
            """, post_id, user_id, content, tags, media
        )
        created_post = await db.fetchrow(
            """
            SELECT * FROM posts WHERE post_id = $1
            """, post_id
        )

    return Status(True, data=dict(created_post) if created_post else None)
