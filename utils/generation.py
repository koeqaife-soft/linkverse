import datetime
import os
from core import server_id
from utils_cy.encryption import encode_shuffle_base64 as encode
from utils_cy.encryption import decode_shuffle_base64 as decode
from utils.encryption import generate_nonce
from utils_cy.encryption import verify_signature, generate_signature
from utils_cy.snowflake import SnowflakeGeneration


SIGNATURE_KEY = os.environ["SIGNATURE_KEY"].encode()


async def generate_token(
    user_id: str, key: str,
    long_term: bool = False,
    secret: str = "12",
    session_id: str = "abc"
) -> str:
    key_num, key = key.split(":", 1)
    expiration = int((
        datetime.datetime.now(datetime.UTC) +
        (datetime.timedelta(hours=1) if not long_term
         else datetime.timedelta(days=30))
    ).timestamp())

    combined_data = f"{user_id}\0{expiration}\0{secret}\0{session_id}".encode()
    nonce = generate_nonce(8)
    encrypted_data = encode(combined_data, key + nonce)

    signature = generate_signature(encrypted_data, SIGNATURE_KEY)

    token = f"{key_num}:{nonce}{encrypted_data}.{signature}"
    return f"LV {token}"


async def decode_token(token: str, key: str) -> dict:
    key_num, key = key.split(":", 1)
    try:
        if not token.startswith("LV "):
            return {
                "success": False,
                "msg": "INVALID_TOKEN"
            }

        token = token[3:]

        if token.count(':') != 1:
            token_key_num = "1"
        else:
            token_key_num, token = token.split(':', 1)

        if token_key_num != key_num:
            return {
                "success": False,
                "msg": "EXPIRED_TOKEN"
            }

        nonce, token = token[:16], token[16:]
        token_parts = token.rsplit('.', 1)
        if len(token_parts) != 2:
            return {
                "success": False,
                "msg": "INVALID_TOKEN_FORMAT"
            }

        token_payload, signature = token_parts

        if not verify_signature(token_payload, signature, SIGNATURE_KEY):
            return {
                "success": False,
                "msg": "INVALID_SIGNATURE"
            }

        decrypted_data = decode(token_payload, key + nonce).decode()
        user_id, expiration, secret, session_id = decrypted_data.split('\0')

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


snowflake = SnowflakeGeneration(server_id)
generate_id = snowflake.generate
parse_id = snowflake.parse
