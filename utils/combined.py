from utils.database import AutoConnection
from utils.moderation import get_audit_data
from utils.cache import posts as cache_posts
from utils.cache import users as cache_users
import utils.posts as posts
import utils.comments as comments
from core import Status, FunctionError
from schemas import Notification
import typing as t


async def get_entity(
    entity_type: str, user_id: str, post_id: str, conn: AutoConnection,
    comment_id: str | None = None,
    users_list: dict[str, dict] | None = None,
    loaded_entity: dict | None = None
) -> Status[dict]:
    if loaded_entity is None:
        fetch_func = (
            cache_posts.get_post if entity_type == "post"
            else comments.get_comment if comment_id is not None
            else comments.get_comment_directly
        )
        entity = (
            await fetch_func(post_id, conn)  # type: ignore
            if entity_type == "post"
            else
            await fetch_func(post_id, comment_id, conn)  # type: ignore
            if comment_id is not None
            else
            await fetch_func(comment_id, conn)
        )
    else:
        if (
            loaded_entity.get("user") is not None
            or loaded_entity.get("is_fav") is not None
            or loaded_entity.get("is_like") is not None
        ):
            return Status(True, loaded_entity)

    fav, reaction = (
        await posts.get_fav_and_reaction(user_id, conn, post_id, comment_id)
    ).data

    data = entity.data.dict if loaded_entity is None else loaded_entity

    async def get_user():
        try:
            return await cache_users.get_user(data["user_id"], conn, True)
        except FunctionError as e:
            if e.code == 404:
                return None
            raise e

    if users_list is None:
        user = await get_user()
        if user:
            data["user"] = user.data.dict
    elif users_list.get(data["user_id"]) is None:
        user = await get_user()
        if user:
            users_list[data["user_id"]] = user.data.dict

    if reaction is not None:
        data["is_like"] = reaction
    if fav:
        data["is_fav"] = fav

    return Status(True, data)


async def get_full_post(
    user_id: str, post_id: str, conn: AutoConnection,
    users_list: dict[str, dict] | None = None,
    loaded: dict | None = None
):
    return await get_entity(
        "post", user_id, post_id, conn, users_list=users_list,
        loaded_entity=loaded
    )


async def get_full_comment(
    user_id: str, post_id: str, comment_id: str,
    conn: AutoConnection,
    users_list: dict[str, dict] | None = None,
    loaded: dict | None = None
):
    return await get_entity(
        "comment", user_id, post_id, conn, comment_id, users_list,
        loaded_entity=loaded
    )


async def preload_items(
    user_id: str, items: list[dict],
    conn: AutoConnection
) -> tuple[list[dict], list[dict], list[tuple]]:
    """
    Preloads a list of items (posts and comments) and returns the data
    """
    posts_data: list[dict] = []
    comments_data: list[dict] = []
    errors: list[tuple[str, str, str]] = []

    for item in items:
        try:
            if item["comment_id"]:
                comment = await get_full_comment(
                    user_id, item["post_id"], item["comment_id"],
                    conn
                )

                comments_data.append(comment.data)
            else:
                post = await get_full_post(
                    user_id, item["post_id"], conn
                )

                posts_data.append(post.data)
        except FunctionError as e:
            errors.append((item["post_id"], item["comment_id"], e.message))

    return posts_data, comments_data, errors


async def preload_notification(
    user_id: str, conn: AutoConnection,
    notification: Notification
) -> Status[Notification]:
    types_actions: dict = {
        "post": lambda post, _: get_full_post(
            user_id, post, conn,
            loaded=t.cast(dict, notification.get("loaded"))
        ),
        "comment": lambda comment, post: get_full_comment(
            user_id, post, comment, conn,
            loaded=t.cast(dict, notification.get("loaded"))
        ),
        "mod_audit": lambda audit, _: get_audit_data(
            audit, False, conn
        )
    }

    data = None
    try:
        data = (
            await types_actions[notification["linked_type"]](
                notification["linked_id"], notification["second_linked_id"]
            )
        ).data
        notification["loaded"] = data  # type: ignore
    except (FunctionError, KeyError):
        pass

    notification["loaded"] = notification.get("loaded") or {}

    if not notification["loaded"].get("user"):
        user = await cache_users.get_user(notification["from_id"], conn, True)
        notification["loaded"]["user"] = user.data.dict

    return Status(True, notification)
