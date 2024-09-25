from dataclasses import dataclass
import datetime
from core import Status
import asyncpg
from utils.generation import generate_id, Action


@dataclass
class Post:
    post_id: int
    user_id: int
    content: str
    created_at: datetime.datetime
    update_at: datetime.datetime
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
        return self.update_at.timestamp()


async def get_post(
    where: dict[str, int | str | bool], db: asyncpg.Connection
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

    return Status(True, data=Post(
        post_id=row['post_id'], user_id=row['user_id'],
        content=row['content'],
        created_at=row['created_at'], update_at=row['updated_at'],
        likes_count=row['likes_count'], comments_count=row['comments_count'],
        tags=row['tags'], media=row['media'],
        status=row['status'], is_deleted=row['is_deleted']
    ))


async def create_post(
    user_id: int, content: str,
    db: asyncpg.Connection,
    tags: list[str] = [],
    media: list[str] = []
) -> Status[int | None]:
    post_id = await generate_id(Action.CREATE_POST)
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO posts (post_id, user_id, content, tags, media)
            VALUES ($1, $2, $3, $4, $5)
            """, post_id, user_id, content, tags, media
        )
    return Status(True, data=post_id)
