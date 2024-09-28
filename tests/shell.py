from typing import Any
import cmd
import requests
import auth
import asyncio
import aiohttp
import traceback
import json


ip = "http://localhost:6169"


class _str(str):
    def f(self, *args, **kwargs):
        return self.format(*args, **kwargs)


class Endpoints:
    def __init__(self) -> None:
        self.login = "/v1/auth/login"
        self.register = "/v1/auth/register"
        self.refresh = "/v1/auth/refresh"
        self.posts = "/v1/posts"
        self.post_actions = "/v1/posts/{}"

    def __getattribute__(self, name: str) -> _str:
        attr = super().__getattribute__(name)
        return _str(f"{ip}{attr}")

    def og(self, name: str) -> Any:
        return super().__getattribute__(name)


class Session:
    is_login = False
    current_token = ""
    current_refresh = ""

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": self.current_token} if self.is_login else {}


def dict_format(
    object: dict[str, Any | dict], indent: int = 0,
    is_main: bool = True, max_key_length: int | None = None
) -> str:
    def get_max_key_len(object: dict, max_len: int = 0):
        max_len = max_len+1
        for key, value in object.items():
            if isinstance(value, dict):
                max_len = max(
                    max_len, get_max_key_len(value, max_len)
                )
            else:
                max_len = max(max_len, len(str(key))+2)
        return max_len

    max_key_length = max_key_length or get_max_key_len(object)
    out: list[str] = []
    prefix = ":: " if is_main else (" " * indent) + "├─"
    last_prefix = ":: " if is_main else (" " * indent) + "└─"

    for index, (key, value) in enumerate(object.items()):
        current_prefix = last_prefix if index == len(object) - 1 else prefix
        if isinstance(value, dict):
            out.append(f"{current_prefix}{key}")
            out.append(dict_format(
                value, indent + (1 if is_main else 2),
                False, max_key_length
            ))
        else:
            out.append(
                f"{current_prefix}{key.ljust(max_key_length - max(indent, 1))}"
                f"--> {value}"
            )

    return "\n".join(out)


def handle_response(r: requests.Response):
    if not r.ok:
        print(r.status_code, r.text)
        return None
    try:
        json = r.json()
    except requests.JSONDecodeError:
        json = {
            "status_code": r.status_code,
            "text": r.text
        }
    return json


class Auth:
    async def _do_register(self, arg):
        while True:
            username = input("Username: ")
            email = input("Email: ")
            password = input("Password: ")
            if len(username) >= 4 and len(email) >= 5 and len(password) >= 8:
                break
            else:
                print("One of the values is too short. Try again.")
        try:
            async with aiohttp.ClientSession() as s:
                _result = await auth.register(username, email, password, s)
            if _result is not None:
                result = json.loads(_result)
                if result["success"]:
                    Session.current_token = result["data"]["access"]
                    Session.current_refresh = result["data"]["refresh"]
                    Session.is_login = True
                    print("Success")
                else:
                    print(result.get("error"))
        except Exception as e:
            traceback.print_exception(e)

    async def _do_login(self, arg):
        while True:
            email = input("Email: ")
            password = input("Password: ")
            if len(email) >= 5 and len(password) >= 8:
                break
            else:
                print("One of the values is too short. Try again.")
        try:
            async with aiohttp.ClientSession() as s:
                _result = await auth.login(email, password, s)
            if _result is not None:
                result = json.loads(_result)
                if result["success"]:
                    Session.current_token = result["data"]["access"]
                    Session.current_refresh = result["data"]["refresh"]
                    Session.is_login = True
                    print("Success")
                else:
                    print(result.get("error"))
        except Exception as e:
            traceback.print_exception(e)

    async def _do_refresh(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        try:
            async with aiohttp.ClientSession() as s:
                _result = await auth.refresh(Session.current_refresh, s)
            if _result is not None:
                result = json.loads(_result)
                if result["success"]:
                    Session.current_token = result["data"]["access"]
                    Session.current_refresh = result["data"]["refresh"]
                    Session.is_login = True
                    print("Success")
                else:
                    print(result.get("error"))
        except Exception as e:
            traceback.print_exception(e)

    def do_logout(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        Session.is_login = False
        Session.current_refresh = ""
        Session.current_token = ""
        print("Success")

    def do_get_tokens(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        print(dict_format({
            "access": Session.current_token,
            "refresh": Session.current_refresh
        }))


class Posts:
    def do_create_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        data = {
            "content": input("Content: ")
        }
        r = requests.post(Endpoints().posts, json=data,
                          headers=Session().headers)

        result = handle_response(r)
        if result:
            print(dict_format(result))

    def do_get_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        r = requests.get(
            Endpoints().post_actions.f(arg),
            headers=Session().headers
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def do_delete_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        r = requests.delete(
            Endpoints().post_actions.f(arg),
            headers=Session().headers
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def do_update_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return
        data = {}
        _content = input("Content: ")

        _tags = input("Tags: ")
        _tags = _tags.split(",") if _tags.strip() else []

        _media = input("Media: ")
        _media = _media.split(",") if _media.strip() else []

        if _content:
            data["content"] = _content
        if _tags:
            data["tags"] = _tags
        if _media:
            data["media"] = _media
        r = requests.patch(
            Endpoints().post_actions.f(arg),
            headers=Session().headers, json=data
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))


class Commands(Auth, Posts):
    ...


class Shell(cmd.Cmd, Commands):
    prompt = "-> "

    def do_check(self, arg):
        try:
            requests.get(ip, timeout=5)
            print(True)
        except requests.ConnectionError:
            print(False)

    def do_exit(self, arg):
        print("Exiting...")
        return True

    def do_help(self, arg: str):
        ...

    def default(self, line):
        command, *args = line.split()
        method = getattr(self, f"_do_{command}", None)

        if method is not None:
            if asyncio.iscoroutinefunction(method):
                asyncio.run(method(" ".join(args)))
            else:
                method(" ".join(args))
        else:
            super().default(line)


if __name__ == "__main__":
    shell = Shell()
    shell.cmdloop()
