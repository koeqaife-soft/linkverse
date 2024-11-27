# cython: language_level=3

from random import Random
import string
from hashlib import sha256
import hmac

cdef str BASE62_ALPHABET = string.digits + string.ascii_letters
cdef int BASE62_LEN = len(BASE62_ALPHABET)
cdef _random = Random()

cpdef str encode_base62(bytes data):
    cdef int base = BASE62_LEN
    cdef unsigned long long num = 0
    cdef int i, rem
    cdef list base62 = []

    for i in range(len(data)):
        num = (num << 8) | data[i]

    if num == 0:
        return BASE62_ALPHABET[0:1]

    while num:
        rem = num % base
        num //= base
        base62.append(BASE62_ALPHABET[rem])

    return ''.join(reversed(base62))


cpdef bytes decode_base62(str encoded):
    cdef int base = BASE62_LEN
    cdef unsigned long long num = 0
    cdef int i, index

    for i in range(len(encoded)):
        index = BASE62_ALPHABET.index(encoded[i])
        num = num * base + index

    cdef int byte_length = (num.bit_length() + 7) // 8

    cdef bytearray result = bytearray(byte_length)
    for i in range(byte_length):
        result[byte_length - 1 - i] = num & 0xFF
        num >>= 8

    return bytes(result)


cpdef bytes prepare_key(str key):
    cdef bytearray key_bytes = bytearray(key.encode('utf-8'))
    cdef bytes hash_result = sha256(key_bytes).digest()

    return hash_result


cpdef str generate_signature(str data, bytes key):
    cdef bytes digest = hmac.new(key, data.encode(), sha256).digest()
    return encode_base62(digest)


cpdef bint verify_signature(str token_payload, str signature, bytes key):
    cdef str expected_signature = generate_signature(token_payload, key)
    return expected_signature == signature


cpdef str generate_nonce(int length=4):
    cdef str alphabet = BASE62_ALPHABET
    cdef str result = ''
    cdef int i
    
    for i in range(length):
        result += _random.choice(alphabet)
    
    return result


cpdef str generate_alphabet(str seed, bytes nonce = b""):
    cdef bytes _seed = prepare_key(seed)

    cdef _random = Random()
    _random.seed(_seed + nonce)
    
    cdef list alphabet = list(BASE62_ALPHABET)
    _random.shuffle(alphabet)
    return ''.join(alphabet)
