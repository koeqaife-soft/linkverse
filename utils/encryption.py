import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
import os
from functools import lru_cache


def generate_chacha20_key() -> bytes:
    return os.urandom(32)


@lru_cache(maxsize=4)
def prepare_key(key: str) -> bytes:
    key_bytes = key.encode()
    if len(key_bytes) != 32:
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(key_bytes)
        return digest.finalize()
    return key_bytes


def chacha20_encrypt(message: bytes, key: bytes | str) -> str:
    if isinstance(key, str):
        key = prepare_key(key)

    nonce = os.urandom(16)
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ct = encryptor.update(message) + encryptor.finalize()
    return base64.urlsafe_b64encode(nonce + ct).decode()


def chacha20_decrypt(encrypted_message: str, key: bytes | str) -> bytes:
    if isinstance(key, str):
        key = prepare_key(key)

    _encrypted_message = base64.urlsafe_b64decode(encrypted_message)
    nonce, ct = _encrypted_message[:16], _encrypted_message[16:]
    cipher = Cipher(
        algorithms.ChaCha20(key, nonce),
        mode=None,
        backend=default_backend()
    )
    decryptor = cipher.decryptor()
    return decryptor.update(ct) + decryptor.finalize()
