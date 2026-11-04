"""Variable-capacity works carrying fixed-size fountain frame batches (v2).

The existing dynamics alphabet is unchanged. Length, zero padding, and the
complete music context are authenticated; no payload is stored in metadata.
"""
import hmac
import struct

from ... import DecodeError
from ..v1 import schools, fountain

DOMAIN = b'scheherazade/school-series/v2\0'
OVERHEAD = 20


def encode(root, frame, key):
    return encode_many(root, [frame], key)


def encode_many(root, frames, key):
    frames = list(frames)
    if not frames or len({len(f) for f in frames}) != 1:
        raise ValueError('nonempty equal-sized fountain frames required')
    identities = [fountain.unpack(f, key) for f in frames]
    if len({(s, k, size, total) for s, i, k, size, total, v in identities}) != 1:
        raise ValueError('mixed fountain snapshots/dimensions')
    size = schools.capacity(root)
    if sum(map(len, frames)) + OVERHEAD > size:
        raise ValueError('fountain frame exceeds dynamics capacity')
    body = (struct.pack('>II', len(frames[0]), len(frames)) + b''.join(frames)).ljust(size - 12, b'\0')
    tag = hmac.digest(fountain.mac_key(key), DOMAIN + schools.context(root) + body, 'sha256')[:12]
    return schools.encode(root, body + tag)


def decode(root, key):
    frames = decode_many(root, key)
    if len(frames) != 1:
        raise DecodeError('expected one frame')
    return frames[0]


def decode_many(root, key):
    block = schools.decode(root)
    if len(block) < OVERHEAD:
        raise DecodeError('truncated dynamics series frame')
    body, tag = block[:-12], block[-12:]
    expected = hmac.digest(fountain.mac_key(key), DOMAIN + schools.context(root) + body, 'sha256')[:12]
    if not hmac.compare_digest(tag, expected):
        raise DecodeError('dynamics series work authentication failed')
    size, count = struct.unpack('>II', body[:8])
    end = 8 + size * count
    if not fountain.OVERHEAD < size or count < 1 or end > len(body) or any(body[end:]):
        raise DecodeError('invalid dynamics series length/padding')
    frames = [body[i:i+size] for i in range(8, end, size)]
    identities = [fountain.unpack(f, key) for f in frames]
    if len({(s, k, size, total) for s, i, k, size, total, v in identities}) != 1:
        raise DecodeError('mixed fountain snapshots/dimensions')
    return frames
