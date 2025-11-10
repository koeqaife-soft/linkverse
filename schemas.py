from typing import TypedDict, Any
from enum import Enum


class ListsDefault(TypedDict):
    has_more: bool
    next_cursor: str | None


class FollowedItem(TypedDict):
    created_at: str
    followed_to: str


class FollowedList(ListsDefault, TypedDict):
    followed: list[FollowedItem]


class FavoriteItem(TypedDict):
    post_id: str
    comment_id: str
    created_at: str


class FavoriteList(ListsDefault, TypedDict):
    favorites: list[FavoriteItem]


class ReactionItem(TypedDict):
    post_id: str
    comment_id: str
    created_at: str
    is_like: bool


class ReactionList(ListsDefault, TypedDict):
    reactions: list[ReactionItem]


class PostsList(TypedDict):
    next_cursor: str | None
    posts: list[str]


class NotificationType(str, Enum):
    NEW_COMMENT = "new_comment"
    FOLLOWED = "followed"
    MOD_DELETED_COMMENT = "mod_deleted_comment"
    MOD_DELETED_POST = "mod_deleted_post"


class NotificationBase(TypedDict, total=True):
    id: str
    from_id: str
    message: str | None
    type: NotificationType | str
    linked_type: str | None
    linked_id: str | None
    second_linked_id: str | None
    unread: bool


class Notification(NotificationBase, TypedDict, total=False):
    loaded: Any


class NotificationList(TypedDict):
    notifications: list[Notification]
    has_more: bool
    next_cursor: str | None
