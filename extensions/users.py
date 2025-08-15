import asyncpg
from quart import Blueprint, Quart, Response
from core import FunctionError, response, Global, route
from quart import g
import utils.users as users
import utils.posts as posts
from utils.cache import users as cache_users
from utils.database import AutoConnection
from utils.realtime import RealtimeManager
import utils.combined as combined
import typing as t

bp = Blueprint('users', __name__)
gb = Global()
pool: asyncpg.Pool = gb.pool
rt_manager: RealtimeManager = gb.rt_manager


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
        raise FunctionError("INCORRECT_DATA", 400, None)

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
            posts, comments, errors = await combined.preload_items(
                g.user_id, t.cast(list[dict], favorites), conn
            )
            response_data.update({
                k: v for k, v in {
                    "posts": posts,
                    "comments": comments,
                    "errors": errors
                }.items() if v
            })
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
            posts, comments, errors = await combined.preload_items(
                g.user_id, t.cast(list[dict], reactions), conn
            )
            response_data.update({
                k: v for k, v in {
                    "posts": posts,
                    "comments": comments,
                    "errors": errors
                }.items() if v
            })
        else:
            response_data.update({"reactions": reactions})

    return response(data=response_data, cache=True), 200


@route(bp, "/users/me/following", methods=["GET"])
async def get_following() -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    preload = params.get("preload", False)

    async with AutoConnection(pool) as conn:
        result = await users.get_followed(g.user_id, conn, cursor)

        followed = result.data.get("followed", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "followed"}

        if preload:
            followed_list: list[dict] = []
            errors: list[tuple] = []
            for item in followed:
                try:
                    user = (
                        await cache_users.get_user(item["followed_to"], conn)
                    ).data
                    followed_list.append(user.dict)
                except FunctionError as e:
                    errors.append((item["followed_to"], e.message))
            if followed_list:
                response_data.update({"following": followed_list})
            if errors:
                response_data.update({"errors": errors})
        else:
            response_data.update({"following": followed})

    return response(data=response_data, cache=True), 200


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


@route(bp, "/users/me/notifications", methods=["GET"])
async def get_notifications() -> tuple[Response, int]:
    params: dict = g.params
    cursor = params.get("cursor", None)
    preload = params.get("preload", False)
    limit = params.get("limit", 20)

    async with AutoConnection(pool) as conn:
        result = await users.get_notifications(g.user_id, conn, cursor, limit)
        notifications = result.data.get("notifications", [])
        response_data = {key: val for key, val in result.data.items()
                         if key != "notifications"}
        if preload:
            preloaded = []
            for object in notifications:
                _result = await combined.preload_notification(
                    g.user_id, conn, object
                )
                preloaded.append(_result.data)
            response_data.update({"notifications": preloaded})
        else:
            response_data.update({"notifications": notifications})
    return response(data=response_data, cache=True), 200


@route(bp, "/users/me/notifications/unread", methods=["GET"])
async def get_unread_notifications_count() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        result = await users.get_unread_notifications_count(g.user_id, conn)
        count = result.data
    return response(data={"count": count}, cache=True), 200


@route(bp, "/users/me/notifications/<id>/read", methods=["POST"])
async def read_notification(id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await users.mark_notification_read(g.user_id, id, conn)
        unread_count = await users.get_unread_notifications_count(
            g.user_id, conn
        )

    await rt_manager.publish_event(
        g.user_id, "notification_read",
        {"id": id, "unread": unread_count.data}
    )
    return response(is_empty=True), 204


@route(bp, "/users/me/notifications/read", methods=["POST"])
async def read_all_notifications() -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        await users.mark_all_notifications_read(g.user_id, conn)

    await rt_manager.publish_event(
        g.user_id, "notification_read", {}
    )
    return response(is_empty=True), 204


@route(bp, "/users/<user_id>", methods=["GET"])
async def get_profile(user_id: str) -> tuple[Response, int]:
    async with AutoConnection(pool) as conn:
        user = await cache_users.get_user(user_id, conn)
        followed = await users.is_followed(g.user_id, user_id, conn)
        data = user.data.dict
        if followed.data:
            data["followed"] = True

    return response(data=data, cache=True), 200


@route(bp, "/users/<user_id>/posts", methods=["GET"])
async def get_user_posts(user_id: str) -> tuple[Response, int]:
    params = g.params
    cursor = params.get("cursor", None)
    sort = params.get("sort", None)

    async with AutoConnection(pool) as conn:
        await cache_users.get_user(user_id, conn, True)
        user_posts = (
            await posts.get_user_posts(user_id, cursor, conn, sort)
        ).data
        _posts = []
        for post in user_posts["posts"]:
            _temp = await combined.get_full_post(
                g.user_id, post.post_id, conn,
                loaded=post.dict
            )
            _posts.append(_temp.data)

        result = t.cast(dict, user_posts)
        result["posts"] = _posts
    return response(data=result, cache=True), 200


def load(app: Quart):
    app.register_blueprint(bp)
