import asyncpg
from quart import Blueprint, Quart, Response
from core import FunctionError, response, Global, route
from quart import g
import utils.users as users
import utils.posts as posts
from utils.cache import users as cache_users
from utils.cache import posts as cache_posts
from utils.database import AutoConnection

bp = Blueprint('users', __name__)
_g = Global()
pool: asyncpg.Pool = _g.pool


@route(bp, "/users/me", methods=["GET"])
async def get_profile_me() -> tuple[Response, int]:
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)

    return response(data=user.data.dict, cache=True), 200


@route(bp, "/users/me", methods=["PATCH"])
async def update_profile_me() -> tuple[Response, int]:
    data = g.data
    user_id = g.user_id
    if not data:
        return response(error=True, error_msg="INCORRECT_DATA"), 400

    async with AutoConnection(pool) as conn:
        await users.update_user(user_id, data, conn)

    await cache_users.delete_user_cache(user_id)

    return response(), 204


async def validate_post_or_comment(
    post_id: str, comment_id: str | None,
    conn: AutoConnection
) -> None:
    if comment_id:
        await posts.get_comment(post_id, comment_id, conn)
    else:
        await posts.get_post(post_id, conn)


@route(bp, "/users/me/favorites", methods=["POST"])
async def add_favorite() -> tuple[Response, int]:
    data = g.data
    post_id = data.get("post_id")
    comment_id = data.get("comment_id")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await validate_post_or_comment(post_id, comment_id, conn)
        await users.add_to_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


@route(bp, "/users/me/favorites", methods=["DELETE"])
async def rem_favorite() -> tuple[Response, int]:
    params: dict = g.params
    post_id = params.get("post_id", "")
    comment_id = params.get("comment_id", "")
    user_id = g.user_id

    async with AutoConnection(pool) as conn:
        await validate_post_or_comment(post_id, comment_id, conn)
        await users.rem_from_favorites(user_id, conn, post_id, comment_id)

    return response(), 204


async def _preload_meta(
    object: posts.Comment | posts.Post | dict,
    conn: AutoConnection
) -> dict:
    if not isinstance(object, dict):
        object = object.dict

    user = await cache_users.get_user(object["user_id"], conn, True)
    object["user"] = user.data.dict

    is_fav, is_like = (
        await posts.get_fav_and_reaction(
            g.user_id, conn, object["post_id"], object.get("comment_id")
        )
    ).data

    if is_like is not None:
        object["is_like"] = is_like
    if is_fav:
        object["is_fav"] = is_fav

    return object


async def _preload_lists(
    items: list[dict], conn: AutoConnection
) -> tuple[list[dict], list[dict], list[tuple]]:
    posts_data: list[dict] = []
    comments_data: list[dict] = []
    errors: list[tuple[str, str, str]] = []

    for item in items:
        try:
            if item["comment_id"]:
                _comment = (await posts.get_comment(
                    item["post_id"], item["comment_id"], conn
                )).data
                comment = await _preload_meta(_comment, conn)

                comments_data.append(comment)
            else:
                _post = (
                    await cache_posts.get_post(item["post_id"], conn)
                ).data
                post = await _preload_meta(_post, conn)

                posts_data.append(post)
        except FunctionError as e:
            if e.message in {"COMMENT_DOES_NOT_EXIST", "POST_DOES_NOT_EXIST"}:
                errors.append((item["post_id"], item["comment_id"], e.message))

    return posts_data, comments_data, errors


@route(bp, "/users/me/favorites", methods=["GET"])
async def get_favorites() -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    type = params.get("type", None)
    preload = params.get("preload", False)

    async with AutoConnection(pool) as conn:
        result = await users.get_favorites(g.user_id, conn, cursor, type)

        favorites = result.data.get("favorites", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "favorites"}

        if preload:
            posts_data, comments_data, errors = await _preload_lists(
                favorites, conn
            )
            if posts_data:
                response_data.update({"posts": posts_data})
            if comments_data:
                response_data.update({"comments": comments_data})
            if errors:
                response_data.update({"errors": errors})
        else:
            response_data.update({"favorites": favorites})

    return response(data=response_data, cache=True), 200


@route(bp, "/users/me/reactions", methods=["GET"])
async def get_reactions() -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    type = params.get("type", None)
    is_like = params.get("is_like", None)
    preload = params.get("preload", False)

    async with AutoConnection(pool) as conn:
        result = await users.get_reactions(
            g.user_id, conn, cursor, type, is_like
        )

        reactions = result.data.get("reactions", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "reactions"}

        if preload:
            posts_data, comments_data, errors = await _preload_lists(
                reactions, conn
            )
            if posts_data:
                response_data.update({"posts": posts_data})
            if comments_data:
                response_data.update({"comments": comments_data})
            if errors:
                response_data.update({"errors": errors})
        else:
            response_data.update({"reactions": reactions})

    return response(data=response_data, cache=True), 200


@route(bp, "/users/<user_id>", methods=["GET"])
async def get_profile(user_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)
        followed = await users.is_followed(g.user_id, user_id, conn)
        data = user.data.dict
        if followed.data:
            data["followed"] = True

    return response(data=data, cache=True), 200


@route(bp, "/users/me/following/<target_id>", methods=["POST"])
async def follow_user(target_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_users.get_user(target_id, conn, True)
        await users.follow(g.user_id, target_id, conn)

    return response(is_empty=True), 204


@route(bp, "/users/me/following/<target_id>", methods=["DELETE"])
async def unfollow_user(target_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await cache_users.get_user(target_id, conn, True)
        await users.unfollow(g.user_id, target_id, conn)

    return response(is_empty=True), 204


def load(app: Quart):
    app.register_blueprint(bp)
