from quart import Blueprint, Quart, Response
from core import response, route
from quart import g
from utils.database import AutoConnection
from utils.reports import create_report
from utils.rate_limiting import rate_limit
from utils.cache import posts as cache_posts
from utils.cache import users as cache_users
from utils import comments
from state import pool

bp = Blueprint('reports', __name__)


@route(bp, "/reports", methods=["POST"])
@rate_limit(5, 60)
async def post_report() -> tuple[Response, int]:
    data = g.data
    reason: str = data["reason"]
    target_id: str = data["target_id"]
    target_type: str = data["target_type"]

    async with AutoConnection(pool) as conn:
        if target_type == "post":
            await cache_posts.get_post(target_id, conn)
        elif target_type == "comment":
            await comments.get_comment_directly(target_id, conn)
        elif target_type == "user":
            await cache_users.get_user(target_id, conn, True)

        await create_report(
            g.user_id, target_id, target_type, reason, conn
        )

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
