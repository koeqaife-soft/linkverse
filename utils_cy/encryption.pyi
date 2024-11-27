def encode_base62(data: bytes) -> str:
    ...


def decode_base62(encoded: str) -> bytes:
    ...


def prepare_key(key: str) -> bytes:
    ...


def verify_signature(token_payload: str, signature: str, key: bytes) -> bool:
    ...


def generate_signature(data: str, key: bytes) -> str:
    ...


def generate_nonce(length: int = 4) -> str:
    ...


def generate_alphabet(seed: str | bytes, nonce: bytes = b"") -> str:
    ...
