from extensions.auth import load as load_auth
from extensions.comments import load as load_comments
from extensions.notifs import load as load_notifs
from extensions.posts import load as load_posts
from extensions.realtime import load as load_realtime
from extensions.storage import load as load_storage
from extensions.users import load as load_users
import typing as t
from logging import getLogger

_logger = getLogger("linkverse.extensions")


__all__ = [
    "load_auth", "load_comments",
    "load_notifs", "load_posts",
    "load_realtime", "load_storage",
    "load_users"
]


def load_all(*args: t.Any, **kwargs: t.Any) -> None:
    for name, value in globals().items():
        if name.startswith("load_") and name != "load_all":
            if callable(value):
                if __debug__:
                    _logger.debug(
                        f"Calling {name}..."
                    )
                value(*args, **kwargs)
