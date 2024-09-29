import asyncio
from dataclasses import dataclass, asdict
import os
import re
from utils.generation import parse_id, generate_id
from utils.generation import generate_token, decode_token
import hashlib
import typing as t
from core import Status
from concurrent.futures import ThreadPoolExecutor
from _types import connection_type

executor = ThreadPoolExecutor()
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


@dataclass
class User:
    username: str
    user_id: int
    email: str
    password_hash: str
    display_name: str | None = None
    avatar_url: str | None = None

    @property
    def created_at(self):
        try:
            return self._created_at
        except AttributeError:
            self._created_at = int(parse_id(self.id)[0])
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
    return os.urandom(length).hex()


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


async def get_user(
    where: dict[str, t.Any], db: connection_type
) -> Status[User | None]:
    if not where:
        raise ValueError("The 'where' dictionary must not be empty")

    conditions: list[str] = []
    values = []
    for key, value in where.items():
        conditions.append(f"{key} = ${len(conditions) + 1}")
        values.append(value)

    query = f"""
        SELECT username, user_id, email, password_hash,
            display_name, avatar_url
        FROM users
        WHERE {' AND '.join(conditions)}
    """
    row = await db.fetchrow(query, *values)

    if row is None:
        return Status(False, message="USER_DOES_NOT_EXIST")

    return Status(True, data=User(**dict(row)))


async def create_user(
    username: str, email: str,
    password: str, db: connection_type
) -> Status[int | None]:
    user = await get_user({"email": email}, db)
    if user.data is not None:
        return Status(False, message="USER_ALREADY_EXISTS")
    password_hash = await store_password(password)
    new_id = await generate_id()
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO users (user_id, username, email, password_hash)
            VALUES ($1, $2, $3, $4)
            """, new_id, username, email, password_hash
        )
    return Status(True, data=new_id)


async def check_username(
    username: str, db: connection_type
) -> Status[None]:
    if len(username) < 4 or not User.validate_username(username):
        return Status(False, message="INCORRECT_FORMAT")
    user = await get_user({"username": username}, db)
    if user.data is not None:
        return Status(False, message="USER_ALREADY_EXISTS")
    return Status(True)


async def login(
    email: str, password: str,
    db: connection_type
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    user = await get_user({"email": email}, db)

    if not user.success or user.data is None:
        return Status(False, message=user.message)
    if not (await check_password(user.data.password_hash, password)):
        return Status(False, message="INCORRECT_PASSWORD")
    new_secret = generate_key()
    access = await generate_token(
        user.data.user_id, secret_key, False,
        new_secret
    )
    refresh = await generate_token(
        user.data.user_id, secret_refresh_key, True,
        new_secret
    )
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret)
            VALUES ($1, $2)
            """, user.data.user_id, new_secret
        )
    return Status(True, {
        "access": access,
        "refresh": refresh
    })


async def create_token(
    user_id: int,
    db: connection_type
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    user = await get_user({"user_id": user_id}, db)
    if user.data is None:
        return Status(False, message="USER_DOES_NOT_EXISTS")
    new_secret = generate_key()
    access = await generate_token(
        user_id, secret_key, False,
        new_secret
    )
    refresh = await generate_token(
        user_id, secret_refresh_key, True,
        new_secret
    )
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret)
            VALUES ($1, $2)
            """, user_id, new_secret
        )
    return Status(True, {
        "access": access,
        "refresh": refresh
    })


async def refresh(
    refresh_token: str, db: connection_type
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    decoded = await decode_token(refresh_token, secret_refresh_key)
    if not decoded["success"]:
        return Status(False, message=decoded.get("msg"))
    elif decoded["is_expired"]:
        return Status(False, message="EXPIRED_TOKEN")

    secret = decoded["secret"]
    user_id = decoded["user_id"]
    result = await db.fetchrow(
        """
        SELECT user_id FROM auth_keys
        WHERE user_id = $1 AND token_secret = $2
        """, user_id, secret
    )

    if result is None:
        return Status(False, message="INVALID_TOKEN")

    new_secret = generate_key()
    access = await generate_token(
        user_id, secret_key,
        False, new_secret)

    refresh = await generate_token(
        user_id, secret_refresh_key,
        True, new_secret
    )

    async with db.transaction():
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret)
            VALUES ($1, $2)
            """, user_id, new_secret
        )
        await db.execute(
            """
            DELETE FROM auth_keys
            WHERE user_id = $1 AND token_secret = $2;
            """, user_id, secret
        )

    return Status(True, {
        "access": access,
        "refresh": refresh
    })


async def check_token(
    token: str, db: connection_type
) -> Status[dict | None]:
    decoded = await decode_token(token, secret_key)
    if not decoded["success"]:
        return Status(False, message=decoded.get("msg"))
    elif decoded["is_expired"]:
        return Status(False, message="EXPIRED_TOKEN")

    result = await db.fetchrow(
        """
        SELECT user_id FROM auth_keys
        WHERE user_id = $1 AND token_secret = $2
        """, decoded["user_id"], decoded["secret"]
    )

    if result is None:
        return Status(False, message="INVALID_TOKEN")

    return Status(True, data=decoded)


async def remove_secret(
    secret: str, user_id: int,
    db: connection_type
) -> Status[None]:
    async with db.transaction():
        await db.execute(
            """
            DELETE FROM auth_keys
            WHERE user_id = $1 AND token_secret = $2;
            """, user_id, secret
        )
    return Status(True)
