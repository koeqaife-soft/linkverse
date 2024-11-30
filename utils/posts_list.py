from core import Status, FunctionError
from utils.database import AutoConnection


async def get_viewed_posts(
    user_id: str,
    conn: AutoConnection
) -> set[str]:
    db = await conn.create_conn()
    viewed_posts_query = """
        SELECT post_id
        FROM user_post_views
        WHERE user_id = $1
        ORDER BY timestamp DESC
        LIMIT 10000
    """
    viewed_posts = await db.fetch(viewed_posts_query, user_id)
    viewed_post_ids = {row['post_id'] for row in viewed_posts}

    return viewed_post_ids


async def get_popular_posts(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    offset: int | None = None,
    hide_viewed: bool | None = None
) -> Status[dict[str, list[tuple[str, str]]]]:
    db = await conn.create_conn()
    hide_viewed = hide_viewed or True
    offset = offset or 0

    if hide_viewed:
        viewed_post_ids = await get_viewed_posts(user_id, conn)

    parameters: list = [limit, offset]

    query = """
        SELECT CAST(post_id AS TEXT) AS post_id,
            CAST(user_id AS TEXT) AS user_id,
            (likes_count - dislikes_count) AS popularity_score
        FROM posts
        WHERE is_deleted = FALSE
    """

    if hide_viewed:
        parameters.append(viewed_post_ids)
        query += " AND post_id NOT IN (SELECT UNNEST($3::text[]))"

    query += """
        ORDER BY popularity_score DESC, comments_count DESC
        LIMIT $1 OFFSET $2
    """

    rows = await db.fetch(
        query, *parameters
    )

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [(row["post_id"], row["user_id"]) for row in rows]
    return Status(True, data={
        "posts": posts
    })


async def get_new_posts(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    offset: int | None = None,
    hide_viewed: bool | None = None
) -> Status[dict[str, list[tuple[str, str]]]]:
    db = await conn.create_conn()
    hide_viewed = hide_viewed or True
    offset = offset or 0

    if hide_viewed:
        viewed_post_ids = await get_viewed_posts(user_id, conn)

    parameters: list = [limit, offset]

    query = """
        SELECT CAST(post_id AS TEXT) AS post_id,
            CAST(user_id AS TEXT) AS user_id,
            created_at
        FROM posts
        WHERE is_deleted = FALSE
    """

    if hide_viewed:
        parameters.append(viewed_post_ids)
        query += " AND post_id NOT IN (SELECT UNNEST($3::text[]))"

    query += """
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
    """

    rows = await db.fetch(
        query, *parameters
    )

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [(row["post_id"], row["user_id"]) for row in rows]
    return Status(True, data={
        "posts": posts
    })


async def mark_post_as_viewed(
    user_id: str, post_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        query = """
            INSERT INTO user_post_views (user_id, post_id)
            VALUES ($1, $2)
            ON CONFLICT (user_id, post_id) DO NOTHING
        """
        await db.execute(query, user_id, str(post_id))
    return Status(True)


async def mark_posts_as_viewed(
    user_id: str, post_ids: list[str],
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()

    query = """
        INSERT INTO user_post_views (user_id, post_id)
        VALUES ($1, $2)
        ON CONFLICT (user_id, post_id) DO NOTHING
    """
    async with db.transaction():
        for post_id in post_ids:
            await db.execute(query, user_id, str(post_id))
    return Status(True)
