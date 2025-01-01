from core import Status, FunctionError
from utils.database import AutoConnection


async def get_popular_posts(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    cursor: str | None = None,
    hide_viewed: bool | None = None
) -> Status[dict[str, list[tuple[str, str]]]]:
    db = await conn.create_conn()
    hide_viewed = True if hide_viewed is None else hide_viewed

    parameters: list = [user_id, limit]

    query = """
        SELECT CAST(post_id AS TEXT) AS post_id,
            CAST(user_id AS TEXT) AS user_id,
            popularity_score
        FROM posts
        WHERE is_deleted = FALSE
    """

    if hide_viewed:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM user_post_views
                WHERE user_post_views.user_id = $1
                AND user_post_views.post_id = posts.post_id
            )
        """
    else:
        if cursor:
            query += " AND popularity_score < $3"
            parameters.append(int(cursor))

    query += """
        ORDER BY popularity_score DESC
        LIMIT $2
    """

    rows = await db.fetch(query, *parameters)

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [(row["post_id"], row["user_id"]) for row in rows]
    next_cursor = str(rows[-1]["popularity_score"]) if rows else None
    return Status(True, data={
        "posts": posts,
        "next_cursor": next_cursor
    })


async def get_new_posts(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    cursor: str | None = None,
    hide_viewed: bool | None = None
) -> Status[dict[str, list[tuple[str, str]]]]:
    db = await conn.create_conn()
    hide_viewed = True if hide_viewed is None else hide_viewed

    parameters: list = [user_id, limit]

    query = """
        SELECT CAST(post_id AS TEXT) AS post_id,
            CAST(user_id AS TEXT) AS user_id,
            created_at
        FROM posts
        WHERE is_deleted = FALSE
    """

    if hide_viewed:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM user_post_views
                WHERE user_post_views.user_id = $1
                AND user_post_views.post_id = posts.post_id
            )
        """
    else:
        if cursor:
            query += " AND created_at < $3"
            parameters.append(cursor)

    query += """
        ORDER BY created_at DESC
        LIMIT $2
    """

    rows = await db.fetch(query, *parameters)

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [(row["post_id"], row["user_id"]) for row in rows]
    next_cursor = rows[-1]["created_at"] if rows else None
    return Status(True, data={
        "posts": posts,
        "next_cursor": next_cursor
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
