from random import randint
import time
from typing import Any
import cmd
import requests
import asyncio

rargs: dict[str, Any] = {}

ip = "http://localhost:6169"


class _str(str):
    def f(self, *args, **kwargs):
        return self.format(*args, **kwargs)


class Endpoints:
    def __init__(self) -> None:
        self.login = "/v1/auth/login"
        self.register = "/v1/auth/register"
        self.refresh = "/v1/auth/refresh"
        self.logout = "/v1/auth/logout"
        self.posts = "/v1/posts"
        self.post_actions = "/v1/posts/{}"
        self.post_reactions = "/v1/posts/{}/reactions"
        self.user = "/v1/users/me"
        self.get_user = "/v1/users/{}"

    def __getattribute__(self, name: str) -> _str:
        attr = super().__getattribute__(name)
        return _str(f"{ip}{attr}")

    def og(self, name: str) -> Any:
        return super().__getattribute__(name)


class Session:
    is_login = False
    cookies = None


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
    def pre_register(self, arg):
        while True:
            username = input("Username: ")
            email = input("Email: ")
            password = input("Password: ")
            if len(username) >= 4 and len(email) >= 5 and len(password) >= 8:
                break
            else:
                print("One of the values is too short. Try again.")
        return {
            "username": username,
            "email": email,
            "password": password
        }

    def _do_register(self, arg, **data):
        r = requests.post(Endpoints().register, json=data, **rargs)
        result = handle_response(r)
        if result:
            if result["success"]:
                Session.cookies = r.cookies
                Session.is_login = True
                print("Success")
            else:
                print(result.get("error"))

    def pre_login(self, arg):
        while True:
            email = input("Email: ")
            password = input("Password: ")
            if len(email) >= 5 and len(password) >= 8:
                break
            else:
                print("One of the values is too short. Try again.")

        return {
            "email": email,
            "password": password
        }

    def _do_login(self, arg, **data):
        r = requests.post(Endpoints().login, json=data, **rargs)
        result = handle_response(r)
        if result:
            if result["success"]:
                Session.cookies = r.cookies
                Session.is_login = True
                print("Success")
            else:
                print(result.get("error"))

    def pre_refresh(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def _do_refresh(self, arg):
        print(Session.cookies)
        r = requests.post(
            Endpoints().refresh, cookies=Session.cookies,
            **rargs
        )
        result = handle_response(r)
        if result:
            if result["success"]:
                Session.cookies = r.cookies
                Session.is_login = True
                print("Success")
            else:
                print(result.get("error"))

    def pre_logout(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def do_logout(self, arg):
        r = requests.post(
            Endpoints().logout, cookies=Session().cookies,
            **rargs
        )
        Session.is_login = False
        Session.cookies = r.cookies
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_get_tokens(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True


class Posts:
    def pre_create_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

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

        return {
            "data": data
        }

    def do_create_post(self, arg, data):
        r = requests.post(
            Endpoints().posts, json=data,
            cookies=Session().cookies, **rargs
        )

        result = handle_response(r)
        if result:
            print(dict_format(result))

    def do_create_test_posts(self, arg):
        for i in range(256):
            self.do_create_post(
                None, {"content": str(randint(i*5, i*100))}
            )

    def pre_get_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def do_get_post(self, arg):
        r = requests.get(
            Endpoints().post_actions.f(arg),
            cookies=Session().cookies, **rargs
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_delete_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def do_delete_post(self, arg):
        r = requests.delete(
            Endpoints().post_actions.f(arg),
            cookies=Session().cookies, **rargs
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_update_post(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True
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
        return {
            "data": data
        }

    def do_update_post(self, arg, data):
        r = requests.patch(
            Endpoints().post_actions.f(arg),
            cookies=Session().cookies, json=data,
            **rargs
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_reaction(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

        is_like = None
        while is_like is None:
            _is_like = input("Is like? (y/n): ")
            if _is_like == "y":
                is_like = True
            elif _is_like == "n":
                is_like = False

        return {
            "is_like": is_like
        }

    def do_reaction(self, arg, is_like):
        data = {
            "is_like": is_like
        }

        r = requests.post(
            Endpoints().post_reactions.f(arg),
            cookies=Session().cookies, json=data,
            **rargs
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_rem_reaction(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def do_rem_reaction(self, arg):
        r = requests.delete(
            Endpoints().post_reactions.f(arg),
            cookies=Session().cookies, **rargs
        )
        result = handle_response(r)
        if result:
            print(dict_format(result))


class Users:
    def pre_me(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True

    def do_me(self, arg):
        r = requests.get(
            Endpoints().user,
            cookies=Session().cookies,
            **rargs
        )

        result = handle_response(r)
        if result:
            print(dict_format(result))

    def pre_change_profile(self, arg):
        if not Session.is_login:
            print("Not in account!")
            return True
        str_values = ["display_name", "avatar_url",
                      "banner_url", "bio", "gender"]
        list_values = ["languages"]

        data = {}
        last_answer = ""
        while last_answer not in ["exit", "send"]:
            print(dict_format({"data": data}))
            print(f"Available values (str): {', '.join(str_values)}")
            print(f"Available values (list): {', '.join(list_values)}")
            print("Type 'send' to change your profile.")

            last_answer = input(">> ")

            if last_answer in str_values:
                value = input("Value: ")
                data[last_answer] = value
            elif last_answer in list_values:
                value = input("Value: ")
                data[last_answer] = value.split(",")

        if last_answer == "exit":
            return True

        return {
            "data": data
        }

    def do_change_profile(self, arg, data):
        r = requests.patch(
            Endpoints().user, json=data,
            cookies=Session().cookies,
            **rargs
        )

        result = handle_response(r)
        if result:
            print(dict_format(result))


class Commands(Auth, Posts, Users):
    ...


class Shell(cmd.Cmd, Commands):
    prompt = "-> "

    def do_check(self, arg):
        try:
            requests.get(ip, timeout=5, **rargs)
            print(True)
        except requests.ConnectionError:
            print(False)

    def do_exit(self, arg):
        print("Exiting...")
        return True

    def do_help(self, arg: str):
        attributes = [
            attr.lstrip("do_").lstrip("_do_")
            for attr in dir(self)
            if attr.startswith(('do_', '_do_'))
        ]
        print(', '.join(attributes))

    def cmdloop(self, intro=None):
        if intro:
            print(intro)
        while True:
            try:
                super(Shell, self).cmdloop(intro="")
                break
            except KeyboardInterrupt:
                print("^C")

    def onecmd(self, line: str):
        cmd, arg, line = self.parseline(line)
        if not line or cmd is None or arg is None:
            return self.emptyline()
        self.lastcmd = line if line != "EOF" else ""
        if cmd == "":
            return self.default(line)

        pre_func = getattr(self, 'pre_' + cmd, None)
        _pre_func_return = None
        kwargs = {}
        if pre_func:
            _pre_func_return = pre_func(arg)
        if _pre_func_return is True:
            return

        if isinstance(_pre_func_return, dict):
            kwargs = _pre_func_return

        func = getattr(
            self, 'do_' + cmd, getattr(self, '_do_' + cmd, None)
        )
        if func is None:
            return self.default(line)

        start = time.perf_counter()
        if asyncio.iscoroutinefunction(func):
            result = asyncio.run(func(arg, **kwargs))
        else:
            result = func(arg, **kwargs)
        print(f"Time: {round(time.perf_counter()-start, 5)} sec")
        return result


if __name__ == "__main__":
    shell = Shell()
    shell.cmdloop()
