def encode_base64(data: bytes) -> str:
    ...


def decode_base64(encoded: str) -> bytes:
    ...


def prepare_key(key: str) -> bytes:
    ...


def verify_signature(token_payload: str, signature: str, key: bytes) -> bool:
    ...


def generate_signature(data: str, key: bytes) -> str:
    ...


def encode_shuffle_base64(data: bytes, seed: str) -> str:
    ...


def decode_shuffle_base64(encoded: str, seed: str) -> bytes:
    ...


def encode_shuffle_base85(data: bytes, seed: str) -> str:
    ...


def decode_shuffle_base85(encoded: str, seed: str) -> bytes:
    ...
