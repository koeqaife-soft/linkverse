import datetime
import os
from utils.encryption import encode_seeded_base62_parallel as encode
from utils.encryption import decode_seeded_base62_parallel as decode
from utils_cy.encryption import verify_signature, generate_signature
from utils_cy.snowflake import SnowflakeGeneration


SECRET_KEY = os.environ["SIGNATURE_KEY"].encode()


async def generate_token(
    user_id: str, key: str | bytes,
    long_term: bool = False,
    secret: str = "12",
    session_id: str = "abc"
) -> str:
    expiration = int((
        datetime.datetime.now(datetime.UTC) +
        (datetime.timedelta(hours=12) if not long_term
         else datetime.timedelta(days=30))
    ).timestamp())

    combined_data = f"{user_id}.{expiration}.{secret}.{session_id}"
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
        user_id, expiration, secret, session_id = decrypted_data.split('.')

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
            "secret": secret,
            "session_id": session_id
        }
    except (ValueError, IndexError):
        return {
            "success": False,
            "msg": "DECODE_ERROR"
        }


snowflake = SnowflakeGeneration()
generate_id = snowflake.generate
parse_id = snowflake.parse
