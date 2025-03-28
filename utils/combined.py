from utils.database import AutoConnection
from utils.cache import posts as cache_posts
from utils.cache import users as cache_users
import utils.posts as posts
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
            else posts.get_comment
        )
        entity = (
            await fetch_func(post_id, conn) if entity_type == "post"
            else await fetch_func(post_id, comment_id, conn)
        )

    fav, reaction = (
        await posts.get_fav_and_reaction(user_id, conn, post_id, comment_id)
    ).data

    data = entity.data.dict if loaded_entity is None else loaded_entity

    async def get_user():
        return await cache_users.get_user(data["user_id"], conn, True)

    if users_list is None:
        user = await get_user()
        data["user"] = user.data.dict
    elif users_list.get(data["user_id"]) is None:
        user = await get_user()
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
    notification: Notification | dict
) -> Status[dict]:
    notification = t.cast(dict, notification)
    types_actions = {
        "post": lambda post, _: get_full_post(user_id, post, conn),
        "comment": lambda post, comment: (
            get_full_comment(user_id, post, comment, conn)
        )
    }

    data = None
    try:
        data = await types_actions[notification["type"]](
            notification["linked_id"], notification["second_linked_id"]
        ).data
        notification["loaded"] = data
    except FunctionError:
        pass

    return Status(True, notification)
