import asyncio
import base64
from dataclasses import dataclass, asdict
import os
import re
from utils.generation import parse_id, generate_id
from utils.generation import generate_token, decode_token
import hashlib
import typing as t
from core import Status, FunctionError
from concurrent.futures import ThreadPoolExecutor
from utils.database import AutoConnection

executor = ThreadPoolExecutor()
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


@dataclass
class AuthUser:
    username: str
    user_id: str
    email: str
    password_hash: str
    email_verified: bool

    @property
    def created_at(self):
        try:
            return self._created_at
        except AttributeError:
            self._created_at = int(parse_id(self.user_id)[0])
            return self._created_at

    @property
    def dict(self) -> dict:
        _dict = asdict(self)
        _dict["created_at"] = self.created_at
        return _dict

    def __dict__(self):
        return self.dict

    @staticmethod
    def validate_username(nickname: str) -> bool:
        if not re.match(r'^[A-Za-z0-9._]+$', nickname):
            return False

        if '..' in nickname:
            return False
        if '__' in nickname:
            return False

        return True


def generate_key(length: int = 16) -> str:
    return base64.b85encode(os.urandom(length), False).decode()


async def hash_password(password: str, salt: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, hashlib.pbkdf2_hmac, 'sha256',
        password.encode(), salt, 10000
    )


def generate_salt() -> bytes:
    return os.urandom(16)


async def store_password(password: str) -> str:
    salt = generate_salt()
    hashed_password = await hash_password(password, salt)
    return f"{salt.hex()}${hashed_password.hex()}"


async def check_password(stored: str, password: str) -> bool:
    salt_hex, stored_hash_hex = stored.split('$')
    salt = bytes.fromhex(salt_hex)
    stored_hash = bytes.fromhex(stored_hash_hex)
    new_hash = await hash_password(password, salt)
    return new_hash == stored_hash


@t.overload
async def get_user(
    where: dict[str, t.Any], conn: AutoConnection,
    return_bool: t.Literal[True]
) -> Status[bool]:
    ...


@t.overload
async def get_user(
    where: dict[str, t.Any], conn: AutoConnection,
    return_bool: t.Literal[False]
) -> Status[AuthUser]:
    ...


@t.overload
async def get_user(
    where: dict[str, t.Any], conn: AutoConnection
) -> Status[AuthUser]:
    ...


async def get_user(
    where: dict[str, t.Any], conn: AutoConnection,
    return_bool: bool | None = None
) -> Status[bool] | Status[AuthUser]:
    db = await conn.create_conn()
    if not where:
        raise ValueError("The 'where' dictionary must not be empty")

    select = (
        "user_id" if return_bool
        else "username, user_id, email, password_hash, email_verified"
    )
    conditions: list[str] = []
    values = []
    for key, value in where.items():
        conditions.append(f"{key} = ${len(conditions) + 1}")
        values.append(value)

    query = f"""
        SELECT {select}
        FROM users
        WHERE {' AND '.join(conditions)}
    """
    row = await db.fetchrow(query, *values)

    if return_bool:
        return Status(True, data=(row is not None))
    else:
        if row is None:
            raise FunctionError("USER_DOES_NOT_EXIST", 404, None)
        return Status(True, data=AuthUser(**dict(row)))


async def create_user(
    username: str, email: str,
    password: str, conn: AutoConnection
) -> Status[str]:
    db = await conn.create_conn()
    user = await get_user({"email": email}, conn, True)
    if user.data:
        raise FunctionError("USER_ALREADY_EXISTS", 409, None)
    password_hash = await store_password(password)
    new_id = str(generate_id())
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO users (user_id, username, email, password_hash)
            VALUES ($1, $2, $3, $4)
            """, new_id, username, email, password_hash
        )
    return Status(True, data=new_id)


async def check_username(
    username: str, conn: AutoConnection
) -> Status[None]:
    if len(username) < 4 or not AuthUser.validate_username(username):
        raise FunctionError("INCORRECT_FORMAT", 400, None)
    user = await get_user({"username": username}, conn, True)
    if user.data:
        raise FunctionError("USERNAME_EXISTS", 409, None)
    return Status(True)


async def login(
    email: str, password: str,
    conn: AutoConnection
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    db = await conn.create_conn()
    user = await get_user({"email": email}, conn)

    if not (await check_password(user.data.password_hash, password)):
        raise FunctionError("INCORRECT_PASSWORD", 401, None)

    new_secret = generate_key()
    session_id = str(generate_id())
    access = await generate_token(
        user.data.user_id, secret_key, False,
        new_secret, session_id
    )
    refresh = await generate_token(
        user.data.user_id, secret_refresh_key, True,
        new_secret, session_id
    )
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret, session_id)
            VALUES ($1, $2, $3)
            """, user.data.user_id, new_secret, session_id
        )
    return Status(True, {
        "access": access,
        "refresh": refresh
    })


async def create_token(
    user_id: str,
    conn: AutoConnection
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    db = await conn.create_conn()
    await get_user({"user_id": user_id}, conn)

    new_secret = generate_key()
    session_id = str(generate_id())
    access = await generate_token(
        user_id, secret_key, False,
        new_secret, session_id
    )
    refresh = await generate_token(
        user_id, secret_refresh_key, True,
        new_secret, session_id
    )
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret, session_id)
            VALUES ($1, $2, $3)
            """, user_id, new_secret, session_id
        )
    return Status(True, {
        "access": access,
        "refresh": refresh
    })


async def refresh(
    refresh_token: str, conn: AutoConnection
) -> Status[dict[t.Literal["tokens"] | t.Literal["decoded"], dict]]:
    db = await conn.create_conn()
    decoded = await decode_token(refresh_token, secret_refresh_key)
    if not decoded["success"]:
        raise FunctionError(decoded.get("msg"), 400, None)
    elif decoded["is_expired"]:
        raise FunctionError("EXPIRED_TOKEN", 401, None)

    secret = decoded["secret"]
    user_id = decoded["user_id"]
    session_id = decoded["session_id"]
    result = await db.fetchrow(
        """
        SELECT user_id FROM auth_keys
        WHERE user_id = $1
        AND token_secret = $2
        AND session_id = $3
        """, user_id, secret, session_id
    )

    if result is None:
        raise FunctionError("INVALID_TOKEN", 401, None)

    new_secret = generate_key()
    access = await generate_token(
        user_id, secret_key,
        False, new_secret, session_id
    )

    refresh = await generate_token(
        user_id, secret_refresh_key,
        True, new_secret, session_id
    )

    async with db.transaction():
        await db.execute(
            """
            UPDATE auth_keys
            SET token_secret = $2
            WHERE session_id = $1
            """, session_id, new_secret
        )

    return Status(True, {
        "tokens": {
            "access": access,
            "refresh": refresh
        },
        "decoded": decoded
    })


async def check_token(
    token: str, conn: AutoConnection,
    decoded: dict | None = None
) -> Status[dict]:
    db = await conn.create_conn()
    decoded = decoded or await decode_token(token, secret_key)
    if not decoded["success"]:
        raise FunctionError(decoded.get("msg"), 401, None)
    elif decoded["is_expired"]:
        raise FunctionError("EXPIRED_TOKEN", 401, None)

    result = await db.fetchrow(
        """
        SELECT user_id FROM auth_keys
        WHERE user_id = $1
        AND token_secret = $2
        AND session_id = $3
        """, decoded["user_id"], decoded["secret"], decoded["session_id"]
    )

    if result is None:
        raise FunctionError("INVALID_TOKEN", 401, None)

    return Status(True, data=decoded)


async def remove_secret(
    secret: str, user_id: str,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            DELETE FROM auth_keys
            WHERE user_id = $1 AND token_secret = $2;
            """, user_id, secret
        )
    return Status(True)


async def set_email_verified(
    user_id: str,
    is_verified: bool,
    conn: AutoConnection
) -> Status[None]:
    db = await conn.create_conn()
    async with db.transaction():
        await db.execute(
            """
            UPDATE users
            SET email_verified = $1
            WHERE user_id = $2
            """, is_verified, user_id
        )

    return Status(True)
