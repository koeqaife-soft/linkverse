import base64
import time
import typing as t
import secrets
import aiohttp
import os
from utils_cy.encryption import generate_signature, verify_signature

SECRET_KEY = os.environ["SIGNATURE_KEY"].encode()
BREVO_API_KEY = os.environ["BREVO_API_KEY"]


templates = {
    "email_verification": {
        "en-US": 6
    }
}


async def send_email(
    to_email: str,
    template_id: int,
    params: dict[str, t.Any],
    tag: str = "transactional",
    return_data: bool = False
) -> dict[str, t.Any]:
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "X-Mailin-Tag": tag,
    }
    payload = {
        "templateId": template_id,
        "to": [{"email": to_email}],
        "params": params,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            return {
                "status": resp.status,
                "data": await resp.json() if return_data else None,
            }


def new_code(length: int = 6, group: int = 3, sep: str = "-") -> str:
    digits = [
        str(secrets.randbelow(10))
        for _ in range(length)
    ]
    if group > 0:
        parts = ["".join(digits[i:i+group]) for i in range(0, length, group)]
        return sep.join(parts)
    return "".join(digits)


def create_token(
    code: str,
    email: str
) -> str:
    code = code.replace("-", "")
    exp = int(time.time() + 15 * 60)
    combined_data = f"{email}\0{exp}".encode()
    encoded_data = base64.urlsafe_b64encode(combined_data).decode()
    signature = generate_signature(encoded_data + code, SECRET_KEY)
    return f"LV-E {encoded_data}.{signature}"


def verify_token(
    code: str,
    token: str
) -> tuple[str, bool]:
    try:
        code = code.replace("-", "")
        if not token.startswith("LV-E "):
            return ("INVALID_TOKEN", False)
        token = token.removeprefix("LV-E ")
        encoded_data, signature = token.split(".")

        is_correct = verify_signature(
            encoded_data + code, signature, SECRET_KEY
        )
        if not is_correct:
            return ("INCORRECT", False)

        email, exp = base64.urlsafe_b64decode(
            encoded_data
        ).decode().split("\0")
        if time.time() > int(exp):
            return ("EXPIRED", False)

        return (email, True)
    except ValueError:
        return ("INVALID_TOKEN", False)
