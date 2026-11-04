"""Systematic random-linear binary fountain over one already encrypted envelope.

Repair equations use SHAKE256-generated dense GF(2) coefficients. With K+s
independent random equations, rank failure probability is less than 2**-s
(random-oracle model). This is a bounded reference codec, not RaptorQ/LT.
Frame generation is rateless; decoding uses Gaussian elimination, not peeling.
"""
import hashlib
import hmac
import math
import struct

from . import DecodeError, payload

DOMAIN = b'scheherazade/fountain/v1'
HEADER = struct.Struct('>4s32sQIII')
OVERHEAD = HEADER.size + 32
MAX_K = 4096
MAX_CAPACITY = 1024 * 1024


def mac_key(key):
    return hmac.digest(key.private_bytes_raw(), DOMAIN, 'sha256')


def dimensions(total, capacity):
    if not OVERHEAD < capacity <= MAX_CAPACITY:
        raise ValueError('frame capacity must be between 89 bytes and 1 MiB')
    size = capacity - OVERHEAD
    k = (total + size - 1) // size
    if not payload.OVERHEAD <= total <= payload.LIMIT + 65536 or not 1 <= k <= MAX_K:
        raise ValueError('envelope too large for this capacity (maximum 4096 source blocks)')
    return k, size


def recommended_count(total, capacity, loss=0.30):
    if not 0 <= loss < 1:
        raise ValueError('invalid loss fraction')
    k, _ = dimensions(total, capacity)
    return math.ceil((k + 32) / (1 - loss))


def coefficients(snapshot, index, k):
    if index < k:
        return 1 << index
    seed = DOMAIN + snapshot + struct.pack('>QI', index, k)
    return int.from_bytes(hashlib.shake_256(seed).digest((k + 7) // 8), 'big') & ((1 << k) - 1)


class Encoder:
    """Seal once externally, then generate any uint64 frame index on demand."""
    def __init__(self, envelope, capacity, key):
        self.k, self.size = dimensions(len(envelope), capacity)
        self.total = len(envelope)
        self.snapshot = hashlib.sha256(envelope).digest()
        self.key = key
        self.blocks = [int.from_bytes(envelope[i:i+self.size].ljust(self.size, b'\0'), 'big')
                       for i in range(0, len(envelope), self.size)]

    def frame(self, index):
        if not 0 <= index < 2**64:
            raise ValueError('invalid index')
        mask = coefficients(self.snapshot, index, self.k)
        value = 0
        while mask:
            bit = mask & -mask
            value ^= self.blocks[bit.bit_length() - 1]
            mask ^= bit
        body = HEADER.pack(b'SHF1', self.snapshot, index, self.k, self.size, self.total)
        body += value.to_bytes(self.size, 'big')
        return body + hmac.digest(mac_key(self.key), body, 'sha256')


def unpack(frame, key):
    if not OVERHEAD < len(frame) <= MAX_CAPACITY:
        raise DecodeError('invalid fountain frame size')
    body, tag = frame[:-32], frame[-32:]
    if not hmac.compare_digest(tag, hmac.digest(mac_key(key), body, 'sha256')):
        raise DecodeError('fountain frame authentication failed')
    magic, snapshot, index, k, size, total = HEADER.unpack(body[:HEADER.size])
    try:
        expected = dimensions(total, len(frame))
    except ValueError as exc:
        raise DecodeError('invalid fountain dimensions') from exc
    if magic != b'SHF1' or (k, size) != expected:
        raise DecodeError('invalid fountain header')
    return snapshot, index, k, size, total, int.from_bytes(body[HEADER.size:], 'big')


def reconstruct(frames, key):
    """Authenticate every input; duplicates do not add rank. Return ciphertext."""
    identity = None
    rows = {}
    seen = {}
    for frame in frames:
        snapshot, index, k, size, total, value = unpack(frame, key)
        current = snapshot, k, size, total
        if identity is not None and current != identity:
            raise DecodeError('mixed snapshots or frame dimensions')
        identity = current
        if index in seen:
            if seen[index] != value:
                raise DecodeError('conflicting duplicate frame')
            continue
        seen[index] = value
        mask = coefficients(snapshot, index, k)
        while mask:
            pivot = (mask & -mask).bit_length() - 1
            if pivot not in rows:
                rows[pivot] = mask, value
                break
            previous, data = rows[pivot]
            mask ^= previous
            value ^= data
        if not mask and value:
            raise DecodeError('inconsistent equations')
    if identity is None or len(rows) != identity[1]:
        raise DecodeError(f'insufficient independent frames: rank {len(rows)}')
    snapshot, k, size, total = identity
    blocks = [0] * k
    for pivot in reversed(range(k)):
        mask, value = rows[pivot]
        mask ^= 1 << pivot
        while mask:
            bit = mask & -mask
            value ^= blocks[bit.bit_length() - 1]
            mask ^= bit
        blocks[pivot] = value
    padded = b''.join(b.to_bytes(size, 'big') for b in blocks)
    envelope = padded[:total]
    if any(padded[total:]) or hashlib.sha256(envelope).digest() != snapshot:
        raise DecodeError('reconstructed snapshot hash/padding mismatch')
    return envelope


def recover(frames, key):
    return payload.open_envelope(reconstruct(frames, key), key, context=DOMAIN)
