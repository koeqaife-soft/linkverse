import datetime
import time
import os
from utils.encryption import encode_seeded_base62_parallel as encode
from utils.encryption import decode_seeded_base62_parallel as decode
from utils.encryption import verify_signature, generate_signature
from core import get_proc_identity
from atomic import AtomicLong  # type: ignore


SECRET_KEY = os.environ["SIGNATURE_KEY"].encode()


class SnowflakeGeneration:
    epoch = 1725513600000

    def __init__(
        self, server_id: int = 1, pid: int | None = None
    ) -> None:
        self.counter_bits = 12
        self.sid_bits = 5
        self.pid_bits = 5
        self.last_timestamp = -1
        self.counter = AtomicLong()
        self.pid = pid or get_proc_identity()
        self.server_id = server_id

    async def generate(self) -> int:
        counter_bits, pid_bits = self.counter_bits, self.pid_bits
        sid_bits = self.sid_bits
        server_id, pid = self.server_id, self.pid

        timestamp = int(time.time() * 1000) - self.epoch
        if timestamp == self.last_timestamp:
            self.counter.value += 1
            if self.counter.value == (1 << self.counter_bits):
                self.counter.value = 0
                while timestamp <= self.last_timestamp:
                    timestamp = int(time.time() * 1000) - self.epoch
        else:
            self.counter.value = 0

        self.last_timestamp = timestamp

        _pid = pid & ((1 << pid_bits) - 1)

        snowflake_id = (
            (timestamp << (counter_bits + sid_bits + pid_bits)) |
            (_pid << (counter_bits + sid_bits)) |
            (server_id << counter_bits) |
            self.counter.value
        )

        return snowflake_id

    def parse(self, snowflake_id: int | str) -> tuple[float, int, int, int]:
        if isinstance(snowflake_id, str):
            snowflake_id = int(snowflake_id)
        counter_bits, pid_bits = self.counter_bits, self.pid_bits
        sid_bits = self.sid_bits

        timestamp = (
            (snowflake_id >> (counter_bits + sid_bits + pid_bits)) +
            self.epoch
        )

        unique = (
            (snowflake_id >> (counter_bits + sid_bits)) &
            ((1 << pid_bits) - 1)
        )

        server_id = (snowflake_id >> counter_bits) & ((1 << sid_bits) - 1)

        counter = snowflake_id & ((1 << counter_bits) - 1)

        return timestamp/1000, server_id, unique, counter


async def generate_token(
    user_id: str, key: str | bytes,
    long_term: bool = False,
    secret: str = "12"
) -> str:
    expiration = int((
        datetime.datetime.now(datetime.UTC) +
        (datetime.timedelta(hours=12) if not long_term
         else datetime.timedelta(days=30))
    ).timestamp())

    combined_data = f"{user_id}.{expiration}.{secret}"
    encrypted_data = await encode(
        combined_data, key,
        len(combined_data) // 3 + 1
    )

    signature = generate_signature(encrypted_data, SECRET_KEY)

    token = f"{encrypted_data}.{signature}"
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

        decrypted_data = (await decode(token_payload, key)).decode()
        user_id, expiration, secret = decrypted_data.split('.')

        expiration_timestamp = int(expiration)
        current_timestamp = int(
            datetime.datetime.now(datetime.UTC).timestamp()
        )

        is_expired = current_timestamp > expiration_timestamp

        return {
            "success": True,
            "user_id": user_id,
            "is_expired": is_expired,
            "expiration_timestamp": expiration_timestamp,
            "secret": secret
        }
    except (ValueError, IndexError):
        return {
            "success": False,
            "msg": "DECODE_ERROR"
        }


snowflake = SnowflakeGeneration()
generate_id = snowflake.generate
parse_id = snowflake.parse
