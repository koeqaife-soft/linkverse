from abc import ABC, abstractmethod
import re
from typing import overload
import typing as t
import ujson
from dotenv import load_dotenv
from quart import Quart, Blueprint, Response
import os
import uvloop
import asyncio
import multiprocessing
import logging
from colorama import Fore, Style, init
import importlib
import datetime
import glob
from quart_cors import cors
import bleach
from quart_compress import Compress
import hashlib

_logger = logging.getLogger("linkverse")
worker_count = int(os.getenv('_WORKER_COUNT', '1'))
init(autoreset=True)

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
T = t.TypeVar("T")
ALLOWED_TAGS = ["i", "strong", "b", "em", "u", "br", "mark", "blockquote"]


load_dotenv()
app = Quart(__name__)
Compress(app)
app.config['COMPRESS_ALGORITHM'] = 'gzip'
app.config['COMPRESS_LEVEL'] = 6
app.config['COMPRESS_MIN_SIZE'] = 500

allow_origin = ["http://localhost:9000", "http://localhost:9300",
                "http://192.168.1.35:9000", "http://koeqaife.ddns.net:9000"]
app = cors(
    app, allow_origin=allow_origin,
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
    max_age=86400
)
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


def _serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.astimezone(datetime.timezone.utc).isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


@overload
def response(
    *, data: dict = ...
) -> Response:
    ...


@overload
def response(
    *, error: bool, data: dict = {},
    error_msg: str,
    **kwargs
) -> Response:
    ...


@overload
def response(
    *, data: dict = ..., **kwargs
) -> Response:
    ...


def response(
    *, error: bool | None = None,
    data: dict = {},
    error_msg: str | None = None,
    cache: bool = False,
    private: bool = True,
    **kwargs
) -> Response:
    _response = {
        "success": not error,
        "data": data
    }
    if error_msg:
        _response["error"] = error_msg

    response = Response(
        ujson.dumps(_response, default=_serializer),
        content_type="application/json",
        **kwargs
    )

    if cache:
        response.cache_control.private = private
        response.cache_control.public = not private
        response.cache_control.must_revalidate = True
        response.set_etag(generate_etag(data))
    else:
        response.cache_control.no_cache = True
        response.cache_control.no_store = True
        response.cache_control.must_revalidate = True

    return response


def generate_etag(data: dict | str) -> str:
    if isinstance(data, dict):
        return hashlib.md5(
                ujson.dumps(data, default=_serializer, sort_keys=True).encode()
        ).hexdigest()
    else:
        return hashlib.md5(data.encode()).hexdigest()


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


def except_value(
    e: FunctionError,
    code: int | None = None,
    message: str | None = None
) -> None:
    if e.code != code:
        raise e
    if e.message != message:
        raise e
    return None


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
    for k in key.split('.'):
        if not isinstance(d, dict):
            return {}
        d = d.get(k, {})
    return d


def get_options(options: str | dict) -> dict:
    if isinstance(options, dict):
        return options
    _options = options.split(";")
    options = {}
    for option in _options:
        if len(option) <= 1:
            continue
        _splitted = option.split(":", 1)
        options[_splitted[0]] = _splitted[1]

    return options


ReturnType = tuple[bool, t.Any | None]


def validate(
    value: t.Any, options: dict,
    is_parameters: bool = False
) -> ReturnType:
    if value is None:
        return False, None

    validator = Validator(options)

    type = options.get("type", "str")
    _validate = getattr(
        validator,
        (f"validate_{type}" if not is_parameters
         else f"parameters_{type}"),
        validator.validate_str
    )

    _result = _validate(value)

    return _result[0], _result[1] or value


class Validator:
    def __init__(self, options: dict) -> None:
        self.options = options

    def validate_dict(self, value: dict) -> ReturnType:
        return isinstance(value, dict), None

    def validate_bool(self, value: bool) -> ReturnType:
        return isinstance(value, bool), None

    def validate_list(self, value: list) -> ReturnType:
        options = self.options
        if not isinstance(value, list):
            return False, None
        checks = {
            "min_len": lambda s, v: len(s) >= int(v),
            "max_len": lambda s, v: len(s) <= int(v),
            "len": lambda s, v: len(s) == int(v)
        }

        for option, check in checks.items():
            if option in options and not check(value, options[option]):
                return False, None

        return True, None

    def validate_int(self, value: int) -> ReturnType:
        options = self.options
        if not isinstance(value, int):
            return False, None
        checks = {
            "min": lambda s, v: s >= int(v),
            "max": lambda s, v: s <= int(v)
        }

        for option, check in checks.items():
            if option in options and not check(value, options[option]):
                return False, None

        return True, None

    def validate_str(self, value: str) -> ReturnType:
        options = self.options
        if not isinstance(value, str):
            return False, None
        checks = {
            "min_len": lambda s, v: len(s) >= int(v),
            "max_len": lambda s, v: len(s) <= int(v),
            "len": lambda s, v: len(s) == int(v),
            "values": lambda s, v: s in v
        }
        filters = {
            "xss": lambda v: bleach.clean(v, tags=ALLOWED_TAGS)
        }

        if "regex" in options:
            if not re.match(options["regex"], value):
                return False, None

        for option, check in checks.items():
            if option in options and not check(value, options[option]):
                return False, None

        if "filter" in options:
            if isinstance(options["filter"], list):
                for x in options["filter"]:
                    value = filters[x](value)
            if isinstance(options["filter"], str):
                value = filters[options["filter"]](value)

        return True, value

    def validate_email(self, value: str) -> ReturnType:
        options = self.options
        options["min_len"] = 4
        options["max_len"] = 254
        options["regex"] = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return self.validate_str(value)

    def parameters_str(self, value: str) -> ReturnType:
        return self.validate_str(value)

    def parameters_list(self, value: str) -> ReturnType:
        options = self.options
        if not isinstance(value, str):
            return False, None

        if "f_max_len" in options and len(value) > options["f_max_len"]:
            return False, None

        _value = value.split(",")

        checks = {
            "min_len": lambda s, v: len(s) >= int(v),
            "max_len": lambda s, v: len(s) <= int(v),
            "len": lambda s, v: len(s) == int(v)
        }

        for option, check in checks.items():
            if option in options and not check(_value, options[option]):
                return False, None

        v_checks = {
            "v_min_len": lambda s, v: len(s) >= int(v),
            "v_max_len": lambda s, v: len(s) <= int(v),
            "v_len": lambda s, v: len(s) == int(v),
            "is_digit": lambda s, v: v and str(s).isdigit()
        }

        for option, check in v_checks.items():
            if option in options:
                for x in _value:
                    if not check(x, options[option]):
                        return False, None

        return True, None


def are_all_keys_present(source: dict, target: dict) -> bool:
    return all(key in target for key in source)
