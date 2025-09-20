import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, FunctionError
from quart import g
from utils.database import AutoConnection
from utils.moderation import update_appellation_status, get_audit_data
from utils.moderation import assign_next_resource, get_assigned_resource
from utils.moderation import remove_assignation
from utils.reports import mark_all_reports_as, get_reports
from utils.users import Permission, check_permission
from utils.rate_limiting import rate_limit
from utils.combined import get_full_comment, get_full_post

bp = Blueprint('moderation', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool


@route(bp, "/appellation/<id>", methods=["POST"])
@rate_limit(15, 60)
async def send_appellation(id: str) -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        audit = (await get_audit_data(id, False, conn)).data
        if audit.get("towards_to") != user_id:
            raise FunctionError("FORBIDDEN", 403, None)
        if audit.get("appellation_status") == "none":
            await update_appellation_status(
                id, "pending", conn
            )

    return response(is_empty=True), 204


@route(bp, "/moderation/assigned_resource", methods=["GET"])
@rate_limit(60, 60)
async def assigned_resource() -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        has_perm = {
            "post": (await check_permission(
                user_id, Permission.MODERATE_POSTS,
                conn
            )).data,
            "comment": (await check_permission(
                user_id, Permission.MODERATE_COMMENTS,
                conn
            )).data,
        }
        perms = tuple([
            name
            for name, value in has_perm.items()
            if value
        ])
        if not perms:
            return FunctionError(403, "FORBIDDEN", None)
        assigned = await assign_next_resource(user_id, perms, conn)
        if assigned.data is None:
            return response(data={}), 200

        data = dict(assigned.data)
        reports = (
            (await get_reports(data["resource_id"], conn)).data
            if data else []
        )
        data["reports"] = reports
        if data["resource_type"] == "post":
            data["loaded"] = (await get_full_post(
                user_id, data["resource_id"], conn
            )).data
        elif data["resource_type"] == "comment":
            data["loaded"] = (await get_full_comment(
                user_id, None, data["resource_id"], conn
            )).data

    return response(data=data or {}), 200


@route(bp, "/moderation/assigned_resource/<id>/dismiss", methods=["POST"])
@rate_limit(30, 60)
async def assigned_resource_action(
    id: str
) -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        assigned = await get_assigned_resource(user_id, conn)
        if assigned.data["resource_id"] != id:
            raise FunctionError(400, "INVALID_STATE", None)
        await mark_all_reports_as(
            "reviewed", assigned.data["resource_id"], conn
        )
        await remove_assignation(user_id, conn)

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
