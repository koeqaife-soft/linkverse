from abc import ABC, abstractmethod
from typing import overload
import typing as t
import json
from dotenv import load_dotenv
from quart import Quart, Blueprint
import os
import uvloop
import asyncio
import multiprocessing
import logging
from colorama import Fore, Style, init
import importlib
import datetime
import glob

_logger = logging.getLogger("linkverse")
worker_count = int(os.getenv('_WORKER_COUNT', '1'))
init(autoreset=True)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
T = t.TypeVar("T")


load_dotenv()
app = Quart(__name__)
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


def _serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.astimezone(datetime.timezone.utc).isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


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
    return json.dumps(_response, default=_serializer)


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


def error_response(status: Status, ):
    if status.success:
        return response()
    else:
        return response(
            error=True, error_msg=(status.message or "UNKNOWN_ERROR")
        )


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


def setup_logger(logger: logging.Logger | None = None):
    global _logger
    logger = logger or _logger

    handler = logging.StreamHandler()

    formatter = ColoredFormatter(
        '%(asctime)s [%(process)d]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    return logger


class VarProxy(ABC):
    @abstractmethod
    def __getattr__(self, name) -> t.Any:
        ...

    def __setattr__(self, name, value):
        setattr(self._obj, name, value)

    def __call__(self, *args, **kwargs):
        return self._obj(*args, **kwargs)

    def __repr__(self):
        return repr(self._obj)

    def __str__(self):
        return str(self._obj)

    def __delattr__(self, name):
        delattr(self._obj, name)

    def __contains__(self, item):
        return item in self._obj

    def __len__(self):
        return len(self._obj)

    def __iter__(self):
        return iter(self._obj)


class _GlobalVars:
    attrs: dict[str, t.Any] = {}


class Global:
    _instance: t.Optional["Global"] = None

    def __new__(cls) -> "Global":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __getattr__(self, name: str) -> t.Any:
        class _proxy(VarProxy):
            def __getattr__(self, _name) -> t.Any:
                if _name == "_obj":
                    return _GlobalVars.attrs.get(name)
                return getattr(self._obj, _name)
        return _proxy()

    def __setattr__(self, name: str, value: t.Any) -> None:
        _GlobalVars.attrs[name] = value


def get_module_name(file_path: str) -> str:
    base_package = __package__.replace('.', os.sep) if __package__ else ""

    relative_path = os.path.relpath(file_path, start=base_package)

    module_path = os.path.splitext(relative_path)[0]

    return module_path.replace(os.sep, '.')


def load_extensions(dir: str = "./extensions", debug: bool = False):
    files = glob.glob(f"{dir}/*.py")
    for file in files:
        name = get_module_name(file)
        module = importlib.import_module(name, __package__)
        module.load(app)
        if debug:
            _logger.info(f"Module {name} loaded!")


def route(_app: Quart | Blueprint, url_rule: str, **kwargs):
    url_rule = f"/v1/{url_rule.lstrip("/")}"
    return _app.route(url_rule, **kwargs)


def get_value_from_dict(d: dict, key: str) -> dict:
    keys = key.split('.')
    for k in keys:
        d = d.get(k, {})
    return d


def get_options(options_str: str) -> dict:
    _options = options_str.split(";")
    options = {}
    for option in _options:
        if len(option) <= 1:
            continue
        _splitted = option.split(":", 1)
        options[_splitted[0]] = _splitted[1]

    return options


def validate_string(string: str, options: dict) -> bool:
    if not isinstance(string, str):
        if isinstance(string, dict) and options.get("is_dict", "0") == "1":
            return True
        else:
            return False

    length_checks = {
        "min_len": lambda s, v: len(s) >= int(v),
        "max_len": lambda s, v: len(s) <= int(v),
        "len": lambda s, v: len(s) == int(v),
    }

    for option, check in length_checks.items():
        if option in options and not check(string, options[option]):
            return False

    return True


def are_all_keys_present(source: dict, target: dict) -> bool:
    return all(key in target for key in source)
