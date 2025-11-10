import orjson
from utils.database import AutoConnection
from core import FunctionError
from utils.generation import generate_id
from quart import request
import typing as t

type AppellationStatus = t.Literal["none", "pending", "rejected", "approved"]


async def create_log(
    user_id: str,
    towards_to: str,
    metadata: dict,
    old_content: dict,
    target_type: str,
    target_id: str,
    action_type: str,
    reason: str,
    conn: AutoConnection
) -> str:
    db = await conn.create_conn()
    new_id = str(generate_id())

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO mod_audit
            (id, user_id, role_id, towards_to, metadata, old_content,
             target_type, target_id, action_type, reason)
            VALUES (
                $1, $2,
                (SELECT role_id FROM users WHERE user_id = $2),
                $3, $4, $5, $6, $7, $8, $9
            )
            """, new_id, user_id, towards_to,
            orjson.dumps(metadata).decode(),
            orjson.dumps(old_content).decode(),
            target_type, target_id, action_type, reason
        )

    return new_id


def log_metadata() -> dict:
    metadata = {
        "headers": dict(request.headers),
        "args": request.args,
        "fullpath": request.full_path,
        "endpoint": request.endpoint,
        "remote_addr": request.remote_addr
    }
    metadata["headers"]["Authorization"] = "LV ..."
    return metadata


async def get_audit_data(
    audit_id: str,
    full: bool,
    conn: AutoConnection
) -> dict:
    db = await conn.create_conn()

    row = await db.fetchrow(
        f"""
        SELECT id, user_id, old_content, target_type,
               target_id, action_type, reason,
               appellation_status, created_at,
               towards_to
               {", metadata, role_id" if full else ""}
        FROM mod_audit
        WHERE id = $1
        """, audit_id
    )

    row_dict: dict[str, t.Any] = dict(row)  # pyright: ignore
    for key in ["old_content", "metadata"]:
        if key in row_dict.keys():
            row_dict[key] = orjson.loads(row_dict[key])
    row_dict["created_at"] = row_dict["created_at"].timestamp()

    return row_dict


async def update_appellation_status(
    audit_id: str,
    new_status: AppellationStatus,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    async with db.transaction():
        await db.execute(
            """
            UPDATE mod_audit
            SET appellation_status = $1
            WHERE id = $2
            """, new_status, audit_id
        )

    return None


async def assign_next_resource(
    moderator_id: str,
    allowed_types: tuple[str, ...],
    conn: AutoConnection
) -> dict | None:
    db = await conn.create_conn()

    row = await db.fetchrow("""
        SELECT resource_id, resource_type
        FROM mod_assigned_resources
        WHERE assigned_to = $1
        LIMIT 1;
    """, moderator_id)

    if row is not None:
        return {
            "resource_id": row["resource_id"],
            "resource_type": row["resource_type"]
        }

    async with db.transaction():
        row = await db.fetchrow(
            """
            WITH next_resource AS (
                SELECT r.target_id, r.target_type
                FROM reports r
                WHERE r.status = 'pending'
                AND r.target_type = ANY($2::text[])
                AND NOT EXISTS (
                    SELECT 1
                    FROM mod_assigned_resources mar
                    WHERE mar.resource_id = r.target_id
                        AND mar.resource_type = r.target_type
                )
                AND (
                    r.target_type != 'post'
                    OR EXISTS (
                        SELECT 1
                        FROM posts p
                        WHERE p.post_id = r.target_id
                            AND p.is_deleted = FALSE
                    )
                )
                ORDER BY r.created_at + (random() * interval '10 minutes')
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            INSERT INTO mod_assigned_resources
                (resource_id, resource_type, assigned_to)
            SELECT target_id, target_type, $1
            FROM next_resource
            RETURNING *;
            """, moderator_id, allowed_types
        )
        if row is None:
            return None

    return {
        "resource_id": row["resource_id"],
        "resource_type": row["resource_type"]
    }


async def get_assigned_resource(
    moderator_id: str,
    conn: AutoConnection
) -> dict:
    db = await conn.create_conn()

    row = await db.fetchrow("""
        SELECT resource_id, resource_type
        FROM mod_assigned_resources
        WHERE assigned_to = $1
        LIMIT 1;
    """, moderator_id)

    if row is None:
        raise FunctionError("NOT_ASSIGNED_ANYTHING", 400, None)

    return {
        "resource_id": row["resource_id"],
        "resource_type": row["resource_type"]
    }


async def remove_assignation(
    moderator_id: str,
    conn: AutoConnection
) -> None:
    db = await conn.create_conn()

    async with db.transaction():
        await db.execute(
            """
            DELETE FROM mod_assigned_resources
            WHERE assigned_to = $1
            """, moderator_id
        )
