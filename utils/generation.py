import datetime
import threading
import time
import enum
import os
from utils.encryption import chacha20_decrypt as decrypt  # type: ignore
from utils.encryption import chacha20_encrypt as encrypt  # type: ignore
from utils.encryption import verify_signature, generate_signature  # type: ignore # noqa


class Action(enum.IntFlag):
    DEFAULT = 1
    CREATE_USER = 2
    CREATE_MESSAGE = 3
    CREATE_POST = 4
    SESSION = 5


SECRET_KEY = os.environ["SIGNATURE_KEY"].encode()
EPOCH = 1725513600000
COUNTER_BITS = 12
ACTION_BITS = 8
PID_BITS = 8

pid = os.getpid()
last_timestamp = -1
counter = 0
lock = threading.Lock()


def generate_id(
    action: Action = Action.DEFAULT
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

        _pid = pid & ((1 << PID_BITS) - 1)

        snowflake_id = (
            (timestamp << (COUNTER_BITS + ACTION_BITS + PID_BITS)) |
            (_pid << (COUNTER_BITS + ACTION_BITS)) |
            (action << COUNTER_BITS) |
            counter
        )

        return snowflake_id


def parse_id(snowflake_id: int) -> tuple[float, Action, int, int]:
    timestamp = (
        (snowflake_id >> (COUNTER_BITS + ACTION_BITS + PID_BITS)) +
        EPOCH
    )

    unique = (
        (snowflake_id >> (COUNTER_BITS + ACTION_BITS)) &
        ((1 << PID_BITS) - 1)
    )

    action = Action((snowflake_id >> COUNTER_BITS) & ((1 << ACTION_BITS) - 1))

    counter = snowflake_id & ((1 << COUNTER_BITS) - 1)

    return timestamp/1000, action, unique, counter


async def generate_token(
    user_id: int, key: bytes | str,
    long_term: bool = False,
    secret: str = "12"
) -> str:
    expiration = int((
        datetime.datetime.now(datetime.UTC) +
        (datetime.timedelta(hours=24) if not long_term
         else datetime.timedelta(days=7))
    ).timestamp())

    encrypted_user_id = await encrypt(str(user_id).encode(), key)
    encrypted_exp = await encrypt(str(expiration).encode(), key)
    encrypted_secret = await encrypt(secret.encode(), key)

    token_payload = f"{encrypted_user_id}.{encrypted_exp}.{encrypted_secret}"
    signature = generate_signature(token_payload, SECRET_KEY)

    token = f"{token_payload}.{signature}"
    return f"LV {token}"


async def decode_token(token: str, key: bytes | str) -> dict:
    try:
        if not token.startswith("LV "):
            return {
                "success": False,
                "msg": "INVALID_TOKEN"
            }

        token = token[3:]
        token_parts = token.rsplit('.', 1)
        if len(token_parts) != 2:
            return {
                "success": False,
                "msg": "INVALID_TOKEN_FORMAT"
            }

        token_payload, signature = token_parts

        if not verify_signature(token_payload, signature, SECRET_KEY):
            return {
                "success": False,
                "msg": "INVALID_SIGNATURE"
            }

        enc_user_id, enc_expiration, enc_secret = token_payload.split('.')
        user_id = (await decrypt(enc_user_id, key)).decode()
        expiration = (await decrypt(enc_expiration, key)).decode()
        secret = (await decrypt(enc_secret, key)).decode()

        expiration_timestamp = int(expiration)
        current_timestamp = int(
            datetime.datetime.now(datetime.UTC).timestamp()
        )

        is_expired = current_timestamp > expiration_timestamp

        return {
            "success": True,
            "user_id": int(user_id),
            "is_expired": is_expired,
            "expiration_timestamp": expiration_timestamp,
            "secret": secret
        }
    except (ValueError, IndexError):
        return {
            "success": False,
            "msg": "DECODE_ERROR"
        }
