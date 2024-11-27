from functools import lru_cache
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os
import string
import asyncio
from utils_cy.encryption import (  # noqa
    encode_base62, decode_base62,
    prepare_key as _prepare_key,
    generate_nonce,
    generate_alphabet
)

BASE62_ALPHABET = string.digits + string.ascii_letters


@lru_cache
def prepare_key(key: str) -> bytes:
    return _prepare_key(key)


async def _decode_char_to_index(char: str, alphabet: str) -> int:
    try:
        return alphabet.index(char)
    except ValueError:
        return -1


async def encode_alphabet_base62(
    data: bytes | str, alphabet: str | bytes
) -> str:
    if isinstance(data, str):
        data = data.encode()
    if isinstance(alphabet, str):
        alphabet = alphabet.encode()
    num = int.from_bytes(data, byteorder='big', signed=False)

    if num == 0:
        return bytes(alphabet[0]).decode()

    base = len(alphabet)
    base62 = bytearray()

    while num:
        num, rem = divmod(num, base)
        base62.append(alphabet[rem])

    base62.reverse()
    return base62.decode()


async def decode_alphabet_base62(encoded: str, alphabet: str) -> bytes:
    base = len(alphabet)
    char_to_index = bytearray(len(encoded))

    tasks = [
        asyncio.create_task(_decode_char_to_index(char, alphabet))
        for char in encoded
    ]
    indices = await asyncio.gather(*tasks)

    for i, idx in enumerate(indices):
        if idx < 0:
            raise ValueError(
                f"Character '{encoded[i]}' not found in alphabet."
            )
        char_to_index[i] = idx

    num = sum(
        idx * (base ** power)
        for power, idx in enumerate(reversed(char_to_index))
    )

    byte_length = (num.bit_length() + 7) // 8 or 1
    return num.to_bytes(byte_length, byteorder='big')


async def encode_seeded_base62_parallel(
    data: str | bytes, seed: str | bytes,
    group_size: int = 3
) -> str:
    nonce = generate_nonce(12)
    groups = [
        data[i:i + group_size]
        for i in range(0, len(data), group_size)
    ]

    alphabet = generate_alphabet(seed, nonce.encode())

    encoded_groups = await asyncio.gather(
        *(encode_alphabet_base62(group, alphabet) for group in groups)
    )

    return nonce + "-".join(encoded_groups)


async def decode_seeded_base62_parallel(
    encoded: str, seed: str | bytes
) -> bytes:
    nonce, encoded = encoded[:12], encoded[12:]
    groups = encoded.split("-")

    alphabet = generate_alphabet(seed, nonce.encode())

    decoded_groups = await asyncio.gather(
        *(decode_alphabet_base62(group, alphabet) for group in groups)
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


async def aes_encrypt(message: bytes, key: bytes | str) -> str:
    key = prepare_key(key)
    nonce = os.urandom(12)
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce),
        backend=default_backend()
    )
    ct = await asyncio.to_thread(_encrypt_data, cipher, message)
    return encode_base62(nonce + ct)


async def aes_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    key = prepare_key(key)
    _encrypted_message = decode_base62(encrypted_message)
    nonce, ct = _encrypted_message[:12], _encrypted_message[12:]
    cipher = Cipher(
        algorithms.AES(key),
        modes.GCM(nonce),
        backend=default_backend()
    )
    return await asyncio.to_thread(_decrypt_data, cipher, ct)


def _encrypt_data(cipher: Cipher, data: bytes) -> bytes:
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _decrypt_data(cipher: Cipher, data: bytes) -> bytes:
    decryptor = cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()
