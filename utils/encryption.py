from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import os
from functools import lru_cache
import string
import hmac
import hashlib
import random
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


def _generate_nonce(length: int = 4) -> str:
    alphabet = BASE62_ALPHABET
    return ''.join(random.choice(alphabet) for _ in range(length))


def generate_alphabet(seed: str | bytes, nonce: str | bytes = "") -> str:
    _seed = prepare_key(seed)
    if isinstance(nonce, str):
        nonce = nonce.encode()
    _random = random.Random(_seed + nonce)
    alphabet = list(BASE62_ALPHABET)
    _random.shuffle(alphabet)
    return ''.join(alphabet)


async def _decode_char_to_index(char: str, alphabet: str) -> int:
    try:
        return alphabet.index(char)
    except ValueError:
        return -1


async def encode_alphabet_base62(data: bytes | str, alphabet: str) -> str:
    if isinstance(data, str):
        data = data.encode()
    num = int.from_bytes(data, byteorder='big', signed=False)

    if num == 0:
        return alphabet[0]

    base = len(alphabet)
    base62 = []

    while num:
        num, rem = divmod(num, base)
        base62.append(alphabet[rem])

    return ''.join(reversed(base62))


async def decode_alphabet_base62(encoded: str, alphabet: str) -> bytes:
    base = len(alphabet)

    tasks = [
        asyncio.create_task(_decode_char_to_index(char, alphabet))
        for char in encoded
    ]
    char_to_index = await asyncio.gather(*tasks)

    if any(idx < 0 for idx in char_to_index):
        invalid_char = encoded[char_to_index.index(-1)]
        raise ValueError(f"Character '{invalid_char}' not found in alphabet.")

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
    nonce = _generate_nonce(12)
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
