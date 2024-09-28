import asyncpg
from quart import Blueprint, Quart, Response
from core import response, Global, route, error_response
from quart import g
import utils.posts as posts

bp = Blueprint('posts', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/posts", methods=["POST"])
async def create_post() -> tuple[Response, int]:
    data = g.data
    content = data.get('content')

    async with pool.acquire() as db:
        result = await posts.create_post(g.user_id, content, db)

    if not result.success:
        return error_response(result), 500

    return response(data=result.data or {}), 201


@route(bp, "/posts/<int:id>", methods=["GET"])
async def get_post(id: int) -> tuple[Response, int]:
    async with pool.acquire() as db:
        result = await posts.get_post({"post_id": id}, db)

    if not result.success:
        return error_response(result), 400

    if result.data is None:
        return response(error=True, error_msg="UNKNOWN_ERROR"), 500

    return response(data=result.data.to_dict()), 200


@route(bp, "/posts/<int:id>", methods=["DELETE"])
async def delete_post(id: int) -> tuple[Response, int]:
    async with pool.acquire() as db:
        post = await posts.get_post({"post_id": id}, db)
        if not post.success:
            return error_response(post), 400
        if post.data.user_id != g.user_id:  # type: ignore
            return response(error=True, error_msg="FORBIDDEN"), 403
        result = await posts.delete_post(id, db)

    if not result.success:
        return error_response(result), 500

    return response(), 204


@route(bp, "/posts/<int:id>", methods=["PATCH"])
async def update_post(id: int) -> tuple[Response, int]:
    data = g.data
    content: str | None = data.get("content")
    tags: list[str] | None = data.get("tags")
    media: list[str] | None = data.get("media")

    if content is None and tags is None and media is None:
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with pool.acquire() as db:
        post = await posts.get_post({"post_id": id}, db)
        if not post.success:
            return error_response(post), 400
        if post.data.user_id != g.user_id:  # type: ignore
            return response(error=True, error_msg="FORBIDDEN"), 403
        result = await posts.update_post(id, content, tags, media, db)

    if not result.success:
        return error_response(result), 500

    return response(), 204


def load(app: Quart):
    app.register_blueprint(bp)
