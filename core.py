from abc import ABC, abstractmethod
import datetime
from typing import overload
import typing as t
import orjson
from collections import OrderedDict
from dotenv import load_dotenv
from quart import Quart, Blueprint, Response
import os
import uvloop
import asyncio
import multiprocessing
import logging
from colorama import Fore, Style, init
from quart_cors import cors
import xxhash
from utils_cy.validate import Validator

from io import BytesIO
from gzip import GzipFile
import brotli  # type: ignore

_logger = logging.getLogger("linkverse")
worker_count = int(os.getenv('_WORKER_COUNT', '1'))
server_id = int(os.getenv("SERVER_ID", "0"))
total_servers = int(os.getenv("TOTAL_SERVERS", "1"))
init(autoreset=True)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
T = t.TypeVar("T")

load_dotenv()
app = Quart(__name__)

compress_config = {
    "mimetypes": [
        "text/html",
        "text/css",
        "text/xml",
        "application/json",
        "application/javascript",
    ],
    "compress_level": 6,
    "min_size": 500
}

allow_headers = [
    "Upgrade", "Connection",
    "Sec-WebSocket-Key", "Sec-WebSocket-Version",
    "Origin", "Sec-WebSocket-Protocol",
    "Content-Type", "Authorization"
]
app = cors(
    app, allow_origin=["*", "app.sharinflame.com"],
    allow_headers=allow_headers,
    max_age=86400
)
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


async def await_if_cor(v_or_cor: t.Awaitable[T] | T) -> T:
    if asyncio.iscoroutine(v_or_cor):
        return await v_or_cor
    else:
        return v_or_cor  # pyright: ignore[reportReturnType]


async def compress(data, algorithm: str = "br") -> bytes:
    if algorithm == "gzip":
        return await asyncio.to_thread(compress_gzip, data)
    elif algorithm == "br":
        return await asyncio.to_thread(compress_brotli, data)
    else:
        raise ValueError("Unknown algorithm, available: gzip, br")


def compress_gzip(data) -> bytes:
    gzip_buffer = BytesIO()

    with GzipFile(
        mode="wb",
        compresslevel=compress_config["compress_level"],
        fileobj=gzip_buffer,
    ) as gzip_file:
        gzip_file.write(data)

    return gzip_buffer.getvalue()


def compress_brotli(data) -> bytes:
    return brotli.compress(data)


@overload
def response(
    *, data: t.Mapping = ...
) -> Response:
    ...


@overload
def response(
    *, error: t.Literal[True], data: t.Mapping = {},
    error_msg: str,
    **kwargs
) -> Response:
    ...


@overload
def response(
    *, data: t.Mapping = ..., **kwargs
) -> Response:
    ...


@overload
def response(
    *, is_empty: t.Literal[True], **kwargs
) -> Response:
    ...


def response(
    *, error: bool | None = None,
    data: t.Mapping = {},
    error_msg: str | None = None,
    cache: bool = False,
    private: bool = True,
    keep_none: bool = False,
    is_empty: bool = False,
    **kwargs
) -> Response:
    if is_empty:
        response = Response()
        response.headers.clear()
        response.set_data(b"")
        return response

    if not keep_none:
        data = remove_none_values(data)
    data = convert_datetime_to_timestamp(data)

    response_data = {
        "success": not error,
        "data": data
    }
    if error_msg:
        response_data["error"] = error_msg

    response = Response(
        orjson.dumps(response_data),
        content_type="application/json",
        **kwargs
    )

    if cache:
        response.cache_control.private = True if private else None
        response.cache_control.public = not private
        response.cache_control.must_revalidate = True
        response.set_etag(generate_etag(dict(data) | dict(response.headers)))
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True

    return response


def convert_datetime_to_timestamp(d: t.Any) -> t.Any:
    if isinstance(d, dict):
        return {k: convert_datetime_to_timestamp(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [convert_datetime_to_timestamp(v) for v in d]
    elif isinstance(d, datetime.datetime):
        return int(d.timestamp())
    else:
        return d


def remove_none_values(d: t.Any) -> t.Any:
    if isinstance(d, dict):
        return {k: remove_none_values(v) for k, v in d.items()
                if v is not None}
    elif isinstance(d, list):
        return [remove_none_values(v) for v in d]
    else:
        return d


def generate_etag(data: dict | str) -> str:
    if isinstance(data, dict):
        sorted_data = OrderedDict(sorted(data.items()))
        return xxhash.xxh64(orjson.dumps(sorted_data)).hexdigest()
    else:
        return xxhash.xxh64(data.encode()).hexdigest()


class FunctionError(Exception):
    def __init__(
        self, message: str | None, code: int, data: dict | None, *args
    ) -> None:
        self.message = message or "UNKNOWN_ERROR"
        self.code = code
        self.data = data
        super().__init__(message, *args)

    def response(self) -> tuple[Response, int]:
        return response(
            error=True,
            data=self.data or {},
            error_msg=self.message
        ), self.code


def get_proc_identity() -> int:
    _id = multiprocessing.current_process()._identity
    if _id:
        return _id[0]
    else:
        return 0


def is_systemd() -> bool:
    return os.getenv("INVOCATION_ID") is not None


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

        record_name = record.name.removeprefix("linkverse.")

        formatted_message = super().format(record)

        return (
            log_color +
            f"{levelname}{Style.BRIGHT} [{record_name}] " +
            formatted_message +
            Style.RESET_ALL
        )


def setup_logger(logger: logging.Logger | None = None):
    global _logger
    logger = logger or _logger

    handler = logging.StreamHandler()

    id = f"[{get_proc_identity()}/{worker_count}|" \
         f"{server_id + 1}/{total_servers}]"
    if is_systemd():
        fmt = f'{id}: %(message)s'
    else:
        fmt = f'%(asctime)s [%(process)d] {id}: %(message)s'

    formatter = ColoredFormatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)

    logger.setLevel(logging.DEBUG)
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


def route(_app: Quart | Blueprint, url_rule: str, **kwargs):
    url_rule = f"/v1/{url_rule.lstrip("/")}"
    return _app.route(url_rule, **kwargs)


ReturnType = tuple[bool, t.Any | None]


def validate(
    value: t.Any, options: dict,
    is_parameters: bool = False
) -> ReturnType:
    if value is None:
        if options.get("allow_none"):
            return True, None
        return False, None

    validator = Validator(options)

    type = options.get("type", "str")
    _validate = getattr(
        validator,
        (f"validate_{type}" if not is_parameters
         else f"parameters_{type}"),
        validator.validate_str
    )

    try:
        _result = _validate(value)
    except TypeError:
        _result = False, None

    return _result[0], value if _result[1] is None else _result[1]


def are_all_keys_present(source: dict, target: dict) -> bool:
    return all(key in target for key in source)


def flatten_dict(
    d: dict,
    parent_key: str = '',
    level: int = 0,
    max_levels: int = 2
) -> dict:
    if level >= max_levels:
        return {parent_key: d} if parent_key else d

    if parent_key and all(isinstance(v, dict) for v in d.values()):
        new_dict = {}
        for k, v in d.items():
            new_key = f"{parent_key}.{k}"
            new_dict.update(flatten_dict(v, new_key, level + 1, max_levels))
        return new_dict
    else:
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                if all(isinstance(val, dict) for val in v.values()):
                    new_key = f"{parent_key}.{k}" if parent_key else k
                    result.update(
                        flatten_dict(v, new_key, level + 1, max_levels)
                    )
                else:
                    result[k] = v
            else:
                result[k] = v
        return {parent_key: result} if parent_key else result
