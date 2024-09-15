from typing import overload
import typing as t
import json
from dotenv import load_dotenv
from quart import Quart
import os
import uvloop
import asyncio
import multiprocessing
import logging
from colorama import Fore, Style, init

worker_count = int(os.getenv('_WORKER_COUNT', '1'))
init(autoreset=True)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
T = t.TypeVar("T")


load_dotenv()
app = Quart(__name__)
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


@overload
def response(
    *, data: dict = ...
) -> str:
    ...


@overload
def response(
    *, error: bool, data: dict = {},
    error_msg: str
) -> str:
    ...


def response(
    *, error: bool | None = None, data: dict = {},
    error_msg: str | None = None
) -> str:
    _response = {
        "success": not error,
        "data": data
    }
    if error_msg:
        _response["error"] = error_msg
    return json.dumps(_response)


class Status(t.Generic[T]):
    def __init__(
        self, success: bool, data: T = None,  # type: ignore
        message: str | None = None
    ) -> None:
        self.success = success
        self.message = message
        self.data = data

    def __eq__(self, other):
        if isinstance(other, str):
            return self.message == other
        elif isinstance(other, Status):
            if self.message is not None:
                return self.message == other.message
            else:
                return self.data == other.data
        elif isinstance(other, bool):
            return self.success == other
        else:
            return False

    def __bool__(self):
        return self.success

    def __str__(self):
        return str(self.message)

    @property
    def dict(self):
        return {
            "success": self.success,
            "data": self.data,
            "error": self.message
        }


def get_proc_identity() -> int:
    _id = multiprocessing.current_process()._identity
    if _id:
        return _id[0]
    else:
        return 0


class ColoredFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: Fore.WHITE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.COLORS.get(record.levelno, Fore.WHITE)
        levelname = record.levelname[0]
        formatted_message = super().format(record)
        return (
            log_color +
            f"{levelname}{Style.BRIGHT} " +
            formatted_message +
            Style.RESET_ALL
        )


def setup_logger():
    handler = logging.StreamHandler()

    formatter = ColoredFormatter(
        '%(asctime)s [%(process)d]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    return logger
