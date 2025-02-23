from typing import TypedDict


class ListsDefault(TypedDict):
    has_more: bool
    next_cursor: str | None


class FollowedItem(TypedDict):
    created_at: str
    followed_to: str


class FollowedList(TypedDict, ListsDefault):
    followed: list[FollowedItem]


class FavoriteItem(TypedDict):
    post_id: str
    comment_id: str
    created_at: str


class FavoriteList(TypedDict, ListsDefault):
    favorites: list[FavoriteItem]


class ReactionItem(TypedDict):
    post_id: str
    comment_id: str
    created_at: str
    is_like: bool


class ReactionList(TypedDict, ListsDefault):
    reactions: list[ReactionItem]


class PostsList(TypedDict):
    next_cursor: str | None
    posts: list[str]
