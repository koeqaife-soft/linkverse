import orjson
from utils.database import AutoConnection
from core import Status
from utils.generation import generate_id
from quart import request


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
) -> Status[str]:
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

    return Status(True, data=new_id)


def log_metadata() -> Status[dict]:
    metadata = {
        "headers": dict(request.headers),
        "args": request.args,
        "fullpath": request.full_path,
        "endpoint": request.endpoint,
        "remote_addr": request.remote_addr
    }
    return Status(True, metadata)


async def get_audit_data(
    audit_id: str,
    full: bool,
    conn: AutoConnection
) -> Status[dict]:
    db = await conn.create_conn()

    row = await db.fetchrow(
        f"""
        SELECT user_id, old_content, target_type,
               target_id, action_type, reason,
               appellation_status
               {", metadata, towards_to, role_id" if full else ""}
        FROM mod_audit
        WHERE id = $1
        """, audit_id
    )

    row_dict = dict(row)
    for key in ["old_content", "metadata"]:
        if key in row_dict.keys():
            row_dict[key] = orjson.loads(row_dict[key])

    return Status(True, row_dict)
