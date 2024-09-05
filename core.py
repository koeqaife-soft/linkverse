from typing import overload
import typing as t
import json


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
