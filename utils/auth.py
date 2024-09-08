import asyncio
from dataclasses import dataclass
import os
import re
from utils.generation import parse_id, generate_id, Action
from utils.generation import generate_token
from utils.database import Transaction
import hashlib
import aiosqlite
import typing as t
from core import Status
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor()
secret_key = os.environ["SECRET_KEY"]
secret_refresh_key = os.environ["SECRET_REFRESH_KEY"]


@dataclass
class User:
    username: str
    id: int
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
    def dict(self):
        return {
            "username": self.username,
            "display_name": self.display_name,
            "id": self.id,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at
        }

    @staticmethod
    def validate_username(nickname: str) -> bool:
        if not re.match(r'^[A-Za-z.]+$', nickname):
            return False

        if '..' in nickname:
            return False

        return True


def generate_key(length: int = 16) -> str:
    return os.urandom(length).hex()


async def hash_password(password: str, salt: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, hashlib.pbkdf2_hmac, 'sha256',
        password.encode(), salt, 25000
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


async def create_user(
    username: str, email: str,
    password: str, db: aiosqlite.Connection
) -> Status[None]:
    result = await (await db.execute(
        """
        SELECT username FROM users
        WHERE email = ?
        """, (email,)
    )).fetchone()
    if result is not None:
        return Status(False, message="USER_ALREADY_EXISTS")
    password_hash = await store_password(password)
    new_id = generate_id(Action.CREATE_USER)
    async with Transaction(db):
        await db.execute(
            """
            INSERT INTO users (user_id, username, email, password_hash)
            VALUES (?, ?, ?, ?)
            """, (new_id, username, email, password_hash)
        )
    return Status(True)


async def check_username(
    username: str, db: aiosqlite.Connection
) -> Status[None]:
    if len(username) < 8 or not User.validate_username(username):
        return Status(False, message="INCORRECT_FORMAT")
    result = await (await db.execute(
        """
        SELECT username FROM users
        WHERE username = ?
        """, (username,)
    )).fetchone()
    if result is not None:
        return Status(False, message="USER_ALREADY_EXISTS")
    return Status(True)


async def login(
    email: str, password: str,
    db: aiosqlite.Connection
) -> Status[dict[t.Literal["access"] | t.Literal["refresh"], str]]:
    result = await (await db.execute(
        """
        SELECT password_hash, user_id FROM users
        WHERE email = ?
        """, (email,)
    )).fetchone()
    if result is None:
        return Status(False, message="USER_DOES_NOT_EXISTS")
    if not (await check_password(result[0], password)):
        return Status(False, message="INCORRECT_PASSWORD")
    new_secret = generate_key()
    access = await generate_token(result[1], secret_key, False, new_secret)
    refresh = await generate_token(result[1], secret_key, True, new_secret)
    async with Transaction(db):
        await db.execute(
            """
            INSERT INTO auth_keys (user_id, token_secret)
            VALUES (?, ?)
            """, (result[1], new_secret)
        )
    return Status(True, {
        "access": access,
        "refresh": refresh
    })
