from functools import lru_cache
from cryptography.hazmat.primitives.ciphers import (
    Cipher, algorithms, modes, AEADDecryptionContext, AEADEncryptionContext
)
from cryptography.hazmat.backends import default_backend
import os
import string
import asyncio
from utils_cy.encryption import (  # noqa
    encode_base62, decode_base62,
    prepare_key as _prepare_key,
    generate_nonce,
    generate_alphabet,
    generate_index,
    encode_alphabet_base62,
    decode_alphabet_base62
)

BASE62_ALPHABET = string.digits + string.ascii_letters


@lru_cache(maxsize=32)
def prepare_key(key: str) -> bytes:
    return _prepare_key(key)


async def encode_seeded_base62_parallel(
    data: str | bytes, seed: str | bytes,
    group_size: int = 3
) -> str:
    if isinstance(data, str):
        data = data.encode()
    nonce = generate_nonce(12)
    groups = [
        data[i:i + group_size]
        for i in range(0, len(data), group_size)
    ]

    alphabet = generate_alphabet(seed, nonce.encode())

    encoded_groups = await asyncio.gather(
        *(asyncio.to_thread(encode_alphabet_base62, group, alphabet)
          for group in groups)
    )

    return nonce + "-".join(encoded_groups)


async def decode_seeded_base62_parallel(
    encoded: str, seed: str | bytes
) -> bytes:
    nonce, encoded = encoded[:12], encoded[12:]
    groups = encoded.split("-")

    alphabet = generate_alphabet(seed, nonce.encode())
    index = generate_index(alphabet)

    decoded_groups = await asyncio.gather(
        *(asyncio.to_thread(decode_alphabet_base62, group, alphabet, index)
          for group in groups)
    )

    return b''.join(decoded_groups)


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
    return encode_base62(nonce + ct + tag)


async def aes_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    key = prepare_key(key)
    _encrypted_message = decode_base62(encrypted_message)
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
