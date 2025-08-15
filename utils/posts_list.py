from core import Status, FunctionError
from utils.database import AutoConnection
from schemas import PostsList


async def get_popular_posts(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    cursor: str | None = None,
    hide_viewed: bool | None = None
) -> Status[PostsList]:
    db = await conn.create_conn()
    hide_viewed = True if hide_viewed is None else hide_viewed

    if cursor:
        _popularity_score, post_id = cursor.split(",")
        popularity_score = int(_popularity_score)

    parameters: list = [limit, user_id]

    query = """
        SELECT post_id, popularity_score
        FROM posts
        WHERE is_deleted = FALSE AND user_id != $2
    """

    if hide_viewed:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM user_post_views
                WHERE user_post_views.user_id = $2
                AND user_post_views.post_id = posts.post_id
            )
        """
    elif cursor:
        query += """
            AND (
                (popularity_score) < $2 OR
                ((popularity_score) = $2 AND post_id < $3)
            )
        """
        parameters.extend([popularity_score, post_id])

    query += """
        ORDER BY popularity_score DESC, post_id::bigint DESC
        LIMIT $1
    """

    rows = await db.fetch(query, *parameters)

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [row["post_id"] for row in rows]
    last_post = rows[-1]

    next_cursor = (f"{last_post["popularity_score"]},{last_post["post_id"]}"
                   if rows else None)
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
) -> Status[PostsList]:
    db = await conn.create_conn()
    hide_viewed = True if hide_viewed is None else hide_viewed

    parameters: list = [limit, user_id]

    query = """
        SELECT post_id
        FROM posts
        WHERE is_deleted = FALSE AND user_id != $2
    """

    if hide_viewed:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM user_post_views
                WHERE user_post_views.user_id = $2
                AND user_post_views.post_id = posts.post_id
            )
        """
    elif cursor:
        query += " AND post_id < $2"
        parameters.append(cursor)

    query += """
        ORDER BY post_id::bigint DESC
        LIMIT $1
    """

    rows = await db.fetch(query, *parameters)

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [row["post_id"] for row in rows]
    next_cursor = rows[-1]["post_id"] if rows else None
    return Status(True, data={
        "posts": posts,
        "next_cursor": next_cursor
    })


async def get_posts_by_following(
    user_id: str,
    conn: AutoConnection,
    limit: int = 50,
    cursor: str | None = None,
    hide_viewed: bool | None = None
) -> Status[PostsList]:
    db = await conn.create_conn()
    hide_viewed = True if hide_viewed is None else hide_viewed

    parameters: list = [limit, user_id]

    query = """
        SELECT post_id
        FROM posts
        WHERE is_deleted = FALSE AND EXISTS (
            SELECT 1
            FROM followed
            WHERE followed.user_id = $2
            AND followed.followed_to = posts.user_id
        )
    """

    if hide_viewed:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM user_post_views
                WHERE user_post_views.user_id = $2
                AND user_post_views.post_id = posts.post_id
            )
        """
    elif cursor:
        query += " AND post_id < $3"
        parameters.append(cursor)

    query += """
        ORDER BY post_id::bigint DESC
        LIMIT $1
    """

    rows = await db.fetch(query, *parameters)

    if not rows:
        raise FunctionError("NO_MORE_POSTS", 400, None)

    posts = [row["post_id"] for row in rows]
    next_cursor = rows[-1]["post_id"] if rows else None
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
