from extensions.auth import load as load_auth
from extensions.comments import load as load_comments
from extensions.notifs import load as load_notifs
from extensions.posts import load as load_posts
from extensions.storage import load as load_storage
from extensions.users import load as load_users
from extensions.reports import load as load_reports
from extensions.moderation import load as load_moderation
import typing as t
from logging import getLogger

_logger = getLogger("linkverse.extensions")


__all__ = [
    "load_auth", "load_comments",
    "load_notifs", "load_posts",
    "load_storage",
    "load_users", "load_reports",
    "load_moderation"
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
