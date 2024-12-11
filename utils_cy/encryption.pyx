# cython: language_level=3

from hashlib import sha256
import hmac
from base64 import urlsafe_b64decode, urlsafe_b64encode
import hashlib

cpdef str encode_base64(bytes data):
    cdef str encoded = urlsafe_b64encode(data).decode('utf-8')
    return encoded.rstrip('=')


cpdef bytes decode_base64(str encoded):
    cdef int padding_needed = (4 - len(encoded) & 3) & 3
    cdef bytes decoded = urlsafe_b64decode(encoded + '=' * padding_needed)
    return decoded


cpdef bytes prepare_key(str key):
    cdef bytearray key_bytes = bytearray(key.encode('utf-8'))
    cdef bytes hash_result = sha256(key_bytes).digest()

    return hash_result


cpdef str generate_signature(str data, bytes key):
    cdef bytes digest = hmac.new(key, data.encode(), sha256).digest()
    return encode_base64(digest)


cpdef bint verify_signature(str token_payload, str signature, bytes key):
    cdef str expected_signature = generate_signature(token_payload, key)
    return expected_signature == signature


cpdef str encode_shuffle_base64(bytes data, str seed):
    cdef bytes shuffled = shuffle_bytes(data, seed)
    cdef str base64 = encode_base64(shuffled)
    return base64


cpdef bytes decode_shuffle_base64(str encoded, str seed):
    cdef bytes original = decode_base64(encoded)
    cdef bytes unshuffled = unshuffle_bytes(original, seed)
    return unshuffled


cdef bytes shuffle_bytes(bytes data, str key):
    cdef bytearray shuffled = bytearray(data)
    cdef bytes key_hash = hashlib.sha256(key.encode(), usedforsecurity=True).digest()
    cdef int data_len = len(shuffled)
    cdef int i

    cdef memoryview mv_shuffled = memoryview(shuffled)
    cdef memoryview mv_key_hash = memoryview(key_hash)

    for i in range(data_len):
        mv_shuffled[i] ^= mv_key_hash[i % 32]

    return bytes(mv_shuffled)


cdef bytes unshuffle_bytes(bytes shuffled, str key):
    return shuffle_bytes(shuffled, key)


