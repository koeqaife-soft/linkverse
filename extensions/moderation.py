import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
from utils.database import AutoConnection
from utils.moderation import update_appellation_status, get_audit_data
from utils.rate_limiting import rate_limit

bp = Blueprint('moderation', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool


@route(bp, "/appellation/<id>", methods=["POST"])
@rate_limit(15, 60)
async def send_appellation(id: str) -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        audit = await get_audit_data(id, False, conn)
        if not audit.get("user_id") == user_id:
            raise FunctionError("FORBIDDEN", 403, None)
        if audit.get("appellation_status") == "none":
            await update_appellation_status(
                id, "pending", conn
            )

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
