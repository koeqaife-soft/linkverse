from functools import lru_cache
from cryptography.hazmat.primitives.ciphers import (
    Cipher, algorithms, modes, AEADDecryptionContext, AEADEncryptionContext
)
from cryptography.hazmat.backends import default_backend
import os
import string
import asyncio
from utils_cy.encryption import (
    encode_base64, decode_base64,
    prepare_key as _prepare_key
)

BASE62_ALPHABET = string.digits + string.ascii_letters


@lru_cache(maxsize=32)
def prepare_key(key: str) -> bytes:
    return _prepare_key(key)


def generate_nonce(length: int = 16) -> str:
    return os.urandom(length).hex()


def generate_chacha20_key() -> bytes:
    return os.urandom(32)


async def chacha20_encrypt(message: bytes, key: bytes | str) -> str:
    key = prepare_key(key)

    nonce = os.urandom(16)
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )

    ct, _ = await asyncio.to_thread(_encrypt_data, cipher, message)
    return encode_base64(nonce + ct)


async def chacha20_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    key = prepare_key(key)

    _encrypted_message = decode_base64(encrypted_message)
    nonce, ct = _encrypted_message[:16], _encrypted_message[16:]
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )
    decrypted, _ = await asyncio.to_thread(_decrypt_data, cipher, ct)
    return decrypted


async def aes_encrypt(message: bytes, key: bytes | str) -> str:
    key = prepare_key(key)
    nonce = os.urandom(12)
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce),
        backend=default_backend()
    )
    ct, context = await asyncio.to_thread(_encrypt_data, cipher, message)
    tag = context.tag
    return encode_base64(nonce + ct + tag)


async def aes_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    key = prepare_key(key)
    _encrypted_message = decode_base64(encrypted_message)
    nonce, ct, tag = (
        _encrypted_message[:12], _encrypted_message[12:-16],
        _encrypted_message[-16:]
    )
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce, tag),
        backend=default_backend()
    )
    decrypted, _ = await asyncio.to_thread(_decrypt_data, cipher, ct)
    return decrypted


def _encrypt_data(
    cipher: Cipher, data: bytes
) -> tuple[bytes, AEADEncryptionContext]:
    encryptor = cipher.encryptor()
    return (encryptor.update(data) + encryptor.finalize(), encryptor)


def _decrypt_data(
    cipher: Cipher, data: bytes
) -> tuple[bytes, AEADDecryptionContext]:
    decryptor = cipher.decryptor()
    return (decryptor.update(data) + decryptor.finalize(), decryptor)
