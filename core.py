from typing import overload
import typing as t
import json
from dotenv import load_dotenv
from quart import Quart
import os


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
    error_msg: dict[t.Literal["msg"] | t.Literal["code"], str]
) -> str:
    ...


def response(
    *, error: bool | None = None, data: dict = {},
    error_msg: dict | None = None
) -> str:
    _response = {
        "success": not error,
        "data": data
    }
    if error_msg:
        _response["error"] = error_msg
    return json.dumps(_response)
