import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route
from quart import g
from utils.database import AutoConnection
from utils.reports import create_report
from utils.rate_limiting import rate_limit

bp = Blueprint('reports', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool


@route(bp, "/reports", methods=["POST"])
@rate_limit(5, 60)
async def post_report() -> tuple[Response, int]:
    data = g.data
    reason: str = data["reason"]
    target_id: str = data["target_id"]
    target_type: str = data["target_type"]

    async with AutoConnection(pool) as conn:
        await create_report(
            g.user_id, target_id, target_type, reason, conn
        )

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
