import datetime
import random
import threading
import time
import enum
from encryption import chacha20_decrypt, chacha20_encrypt


class Action(enum.IntFlag):
    DEFAULT = 1
    CREATE_USER = 2
    CREATE_MESSAGE = 3
    CREATE_POST = 4
    SESSION = 5


EPOCH = 1725513600000
COUNTER_BITS = 12
ACTION_BITS = 8
UNIQUE_BITS = 8

session_random = random.randint(1, 16)
last_timestamp = -1
counter = 0
lock = threading.Lock()


def generate_id(
    action: Action = Action.DEFAULT,
    unique: int = session_random
) -> int:
    global last_timestamp, counter

    with lock:
        timestamp = int(time.time() * 1000) - EPOCH
        if timestamp == last_timestamp:
            counter = (counter + 1) & ((1 << COUNTER_BITS) - 1)
            if counter == 0:
                while timestamp <= last_timestamp:
                    timestamp = int(time.time() * 1000) - EPOCH
        else:
            counter = 0

        last_timestamp = timestamp

        unique = unique & ((1 << UNIQUE_BITS) - 1)

        snowflake_id = (
            (timestamp << (COUNTER_BITS + ACTION_BITS + UNIQUE_BITS)) |
            (unique << (COUNTER_BITS + ACTION_BITS)) |
            (action << COUNTER_BITS) |
            counter
        )

        return snowflake_id


def parse_id(snowflake_id: int) -> tuple[int, Action, int, int]:
    timestamp = (
        (snowflake_id >> (COUNTER_BITS + ACTION_BITS + UNIQUE_BITS)) +
        EPOCH
    )

    unique = (
        (snowflake_id >> (COUNTER_BITS + ACTION_BITS)) &
        ((1 << UNIQUE_BITS) - 1)
    )

    action = Action((snowflake_id >> COUNTER_BITS) & ((1 << ACTION_BITS) - 1))

    counter = snowflake_id & ((1 << COUNTER_BITS) - 1)

    return timestamp, action, unique, counter


def generate_token(
    user_id: int, key: bytes | str,
    long_term: bool = False
) -> str:
    expiration = str(int((
        datetime.datetime.now(datetime.UTC) +
        (datetime.timedelta(hours=1) if not long_term
         else datetime.timedelta(days=30))
    ).timestamp()))
    encrypted_user_id = chacha20_encrypt(str(user_id).encode(), key)
    encrypted_exp = chacha20_encrypt(expiration.encode(), key)
    token = f"{encrypted_user_id}.{encrypted_exp}"
    return token


def decode_token(token: str, key: bytes | str) -> dict:
    try:
        encrypted_user_id, encrypted_expiration = token.split('.')

        user_id = chacha20_decrypt(encrypted_user_id, key).decode()
        expiration = chacha20_decrypt(encrypted_expiration, key).decode()

        expiration_timestamp = int(expiration)
        current_timestamp = int(
            datetime.datetime.now(datetime.UTC).timestamp()
        )

        is_expired = current_timestamp > expiration_timestamp

        return {
            "success": True,
            "user_id": int(user_id),
            "is_expired": is_expired,
            "expiration_timestamp": expiration_timestamp
        }
    except Exception:
        return {
            "success": True
        }
