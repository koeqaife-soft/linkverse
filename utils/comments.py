from dataclasses import dataclass, asdict
from core import Status, FunctionError
from utils.generation import generate_id, parse_id
import typing as t
from utils.database import AutoConnection
from schemas import ListsDefault


@dataclass
class Comment:
    comment_id: str
    post_id: str
    user_id: str
    content: str
    parent_comment_id: str | None
    likes_count: int
    dislikes_count: int
    type: str

    @property
    def created_at(self) -> float:
        return parse_id(self.comment_id)[0]

    @property
    def dict(self) -> dict:
        dict = asdict(self)
        dict['created_at'] = int(self.created_at)
        return dict

    def __dict__(self):
        return self.dict

    @staticmethod
    def from_dict(object: t.Dict) -> "Comment":
        return Comment(**dict(object))


class CommentList(t.TypedDict, ListsDefault):
    comments: list[Comment]


async def create_comment(
    user_id: str, post_id: str, content: str,
    conn: AutoConnection,
    type: str | None = None
) -> Status[Comment]:
    db = await conn.create_conn()
    comment_id = str(generate_id())
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO comments (comment_id, post_id, user_id, content, type)
            VALUES ($1, $2, $3, $4, $5)
            """, comment_id, post_id, user_id, content, type or "comment"
        )
        comment = await db.fetchrow(
            """
                SELECT comment_id, parent_comment_id, post_id, user_id,
                       content, likes_count, dislikes_count, type
                FROM comments
                WHERE post_id = $1 AND comment_id = $2
            """, post_id, comment_id
        )

    return Status(True, data=Comment.from_dict(comment))


async def get_comment(
    post_id: str, comment_id: str,
    conn: AutoConnection
) -> Status[Comment]:
    db = await conn.create_conn()
    query = """
        SELECT comment_id, parent_comment_id, post_id, user_id, content,
               likes_count, dislikes_count, type
        FROM comments
        WHERE post_id = $1 AND comment_id = $2
    """
    row = await db.fetchrow(query, post_id, comment_id)

    if row is None:
        raise FunctionError("COMMENT_DOES_NOT_EXIST", 404, None)

    return Status(True, data=Comment.from_dict(row))


async def delete_comment(
    post_id: str, comment_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            DELETE FROM comments
            WHERE post_id = $1 AND comment_id = $2
            """, post_id, comment_id
        )
    return Status(True)


async def get_comments(
    post_id: str,
    cursor: str | None,
    user_id: str,
    conn: AutoConnection,
    type: str | None = None
) -> Status[CommentList]:
    db = await conn.create_conn()
    params: list[t.Any] = [post_id, user_id]

    cte_query = """
        WITH ranked_comments AS (
            SELECT comment_id, parent_comment_id, post_id, user_id, content,
                   likes_count, dislikes_count,
                   popularity_score, type,
                   CASE WHEN user_id = $2 THEN 1 ELSE 0 END AS is_user_comment
            FROM comments
            WHERE post_id = $1
        )
    """

    main_query = """
        SELECT * FROM ranked_comments
    """

    if cursor:
        try:
            _is_user, _popularity_score, comment_id = cursor.split(",")
            is_user_comment = int(_is_user)
            popularity_score = int(_popularity_score)
        except ValueError:
            raise FunctionError("INVALID_CURSOR", 400, None)

        main_query += """
            WHERE (is_user_comment < $3 OR
                   (is_user_comment = $3 AND popularity_score < $4) OR
                   (is_user_comment = $3 AND popularity_score = $4
                    AND comment_id < $5))
        """
        params.extend([is_user_comment, popularity_score, comment_id])
        if type:
            main_query += " AND type = $6"
            params.append(type)
    elif type:
        main_query += "WHERE type = $3"
        params.append(type)

    if type == "comment":
        main_query += """
            ORDER BY is_user_comment DESC, popularity_score DESC,
                    comment_id::bigint DESC
        """
    elif type == "update":
        main_query += """
            ORDER BY comment_id::bigint
        """
    else:
        raise FunctionError("UNKNOWN_COMMENT_TYPE", 404, None)

    main_query += """
        LIMIT 21
    """

    rows = await db.fetch(cte_query + main_query, *params)
    if not rows:
        raise FunctionError("NO_MORE_COMMENTS", 200, None)

    has_more = len(rows) > 20
    rows = rows[:20]

    last_row = rows[-1]
    next_cursor = (
        f"{last_row['is_user_comment']},{last_row['popularity_score']}" +
        f",{last_row['comment_id']}"
    )

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
