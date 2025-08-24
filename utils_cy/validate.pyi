import typing as t

ReturnType = tuple[bool, t.Any | None]


class Validator:
    def __init__(self, options: dict) -> None:
        ...

    def validate_dict(self, value: dict) -> ReturnType:
        ...

    def validate_bool(self, value: bool) -> ReturnType:
        ...

    def validate_list(self, value: list) -> ReturnType:
        ...

    def validate_int(self, value: int) -> ReturnType:
        ...

    def validate_str(self, value: str) -> ReturnType:
        ...

    def validate_email(self, value: str) -> ReturnType:
        ...

    def parameters_str(self, value: str) -> ReturnType:
        ...

    def parameters_int(self, value: str) -> ReturnType:
        ...

    def parameters_bool(self, value: str) -> ReturnType:
        ...

    def parameters_list(self, value: str) -> ReturnType:
        ...
