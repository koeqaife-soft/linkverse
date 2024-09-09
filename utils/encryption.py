from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import os
from functools import lru_cache
import string
import hmac
import hashlib
import asyncio

BASE62_ALPHABET = string.digits + string.ascii_letters


def generate_signature(data: str, key: bytes) -> str:
    return encode_base62(
        hmac.new(key, data.encode(), hashlib.sha256).digest()
    )


def verify_signature(token_payload: str, signature: str, key: bytes) -> bool:
    expected_signature = generate_signature(token_payload, key)
    return hmac.compare_digest(expected_signature, signature)


def encode_base62(data: bytes) -> str:
    num = int.from_bytes(data, byteorder='big', signed=False)

    if num == 0:
        return BASE62_ALPHABET[0]

    base62 = []
    base = len(BASE62_ALPHABET)

    while num:
        num, rem = divmod(num, base)
        base62.append(BASE62_ALPHABET[rem])

    return ''.join(reversed(base62))


def decode_base62(encoded: str) -> bytes:
    base = len(BASE62_ALPHABET)
    num = 0

    for char in encoded:
        num = num * base + BASE62_ALPHABET.index(char)

    byte_length = (num.bit_length() + 7) // 8
    return num.to_bytes(byte_length, byteorder='big')


def generate_chacha20_key() -> bytes:
    return os.urandom(32)


@lru_cache(maxsize=16)
def prepare_key(key: str | bytes) -> bytes:
    if isinstance(key, str):
        key = key.encode()

    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(key)
    return digest.finalize()


async def chacha20_encrypt(message: bytes, key: bytes | str) -> str:
    key = prepare_key(key)

    nonce = os.urandom(16)
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )

    ct = await asyncio.to_thread(_encrypt_data, cipher, message)
    return encode_base62(nonce + ct)


async def chacha20_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    key = prepare_key(key)

    _encrypted_message = decode_base62(encrypted_message)
    nonce, ct = _encrypted_message[:16], _encrypted_message[16:]
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )

    return await asyncio.to_thread(_decrypt_data, cipher, ct)


def _encrypt_data(cipher: Cipher, data: bytes) -> bytes:
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _decrypt_data(cipher: Cipher, data: bytes) -> bytes:
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()
