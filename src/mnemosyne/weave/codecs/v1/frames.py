"""Small authenticated transport frames, reusable across art channels.

The envelope is public-key encrypted; frame MACs use a domain-separated key
from the recipient private key (the encoder must therefore have that key).
96-bit HMAC tags bind every frame to the work's canonical context. This is
not an owner signature. Four-byte bundle IDs are routing hints only; final
assembly verifies the complete authenticated envelope before releasing data.
"""
import hashlib
import hmac
import struct
from . import DecodeError, payload

HEADER = struct.Struct('>4sBBH')
OVERHEAD = HEADER.size + 12
DOMAIN = b'scheherazade/multipart/v1'


def mac_key(key):
    return hmac.digest(key.private_bytes_raw(), DOMAIN, 'sha256')


def pack(envelope, index, capacity, key, context):
    chunk = capacity - OVERHEAD
    if chunk <= 0:
        raise ValueError('no room for a whole frame')
    count = (len(envelope)+chunk-1)//chunk
    if not 0 <= index < count <= 255 or len(envelope) > 65535:
        raise ValueError('invalid or oversized bundle')
    data = envelope[index*chunk:(index+1)*chunk]
    header = HEADER.pack(hashlib.sha256(envelope).digest()[:4], index, count, len(envelope))
    body = header + data.ljust(chunk, b'\0')
    return body + hmac.digest(mac_key(key), context + body, 'sha256')[:12]


def unpack(block, key, context):
    if len(block) <= OVERHEAD:
        raise DecodeError('truncated frame')
    body, tag = block[:-12], block[-12:]
    if not hmac.compare_digest(tag, hmac.digest(mac_key(key), context+body, 'sha256')[:12]):
        raise DecodeError('work/frame authentication failed')
    bundle, index, count, total = HEADER.unpack(body[:HEADER.size])
    chunk = len(block)-OVERHEAD
    if not 0 <= index < count or count != (total+chunk-1)//chunk:
        raise DecodeError('invalid frame index/count/length')
    length = min(chunk, total-index*chunk)
    if any(body[HEADER.size+length:]):
        raise DecodeError('nonzero frame padding')
    return {'bundle': bundle, 'index': index, 'count': count, 'total': total,
            'chunk_size': chunk, 'data': body[HEADER.size:HEADER.size+length]}


def assemble(frames, key):
    if not frames:
        raise DecodeError('no frames')
    first = frames[0]
    fields = ('bundle', 'count', 'total', 'chunk_size')
    if any(any(f[k] != first[k] for k in fields) for f in frames):
        raise DecodeError('mixed bundles')
    by_index = {f['index']: f['data'] for f in frames}
    if len(by_index) != len(frames) or set(by_index) != set(range(first['count'])):
        raise DecodeError('missing or duplicate frames')
    envelope = b''.join(by_index[i] for i in range(first['count']))
    if len(envelope) != first['total'] or hashlib.sha256(envelope).digest()[:4] != first['bundle']:
        raise DecodeError('bundle checksum mismatch')
    return payload.open_envelope(envelope, key, context=DOMAIN)
