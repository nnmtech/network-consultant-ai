import msgpack
from typing import Any
import hashlib

def serialize(data: Any) -> bytes:
    return msgpack.packb(data, use_bin_type=True)

def deserialize(data: bytes) -> Any:
    return msgpack.unpackb(data, raw=False)

def generate_stable_key(*parts: Any) -> str:
    serialized = serialize(parts)
    return hashlib.blake2b(serialized, digest_size=16).hexdigest()