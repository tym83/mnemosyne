"""Exact block arithmetic coding for equiprobable style options.

Each slot partitions its interval into radix equal subintervals. The product
of radices is the common integer scale: no floating point or renormalization.
A fixed-size byte block selects the first integer in one binary interval. Decode
reconstructs that interval and rejects noncanonical padding. All slots are
used, including trailing slots. This is a small-work reference codec, not a
streaming implementation or a claim of steganographic indistinguishability.
"""
from math import prod

from . import DecodeError


def _scale(radices):
    if any(type(r) is not int or r < 2 for r in radices):
        raise ValueError('each radix must be an integer >= 2')
    return prod(radices)


def capacity(radices):
    return (_scale(radices).bit_length() - 1) // 8


def encode(data: bytes, radices: list[int]) -> list[int]:
    scale = _scale(radices)
    binary = 1 << (8 * len(data))
    if scale < binary:
        raise ValueError('insufficient channel capacity')
    rank = (int.from_bytes(data, 'big') * scale + binary - 1) // binary
    digits = []
    for radix in reversed(radices):
        rank, digit = divmod(rank, radix)
        digits.append(digit)
    return digits[::-1]


def decode(digits: list[int], radices: list[int], size: int) -> bytes:
    scale = _scale(radices)
    if type(size) is not int or size < 0 or size > capacity(radices):
        raise DecodeError('invalid block size')
    if len(digits) != len(radices):
        raise DecodeError('slot count mismatch')
    rank = 0
    for digit, radix in zip(digits, radices):
        if type(digit) is not int or not 0 <= digit < radix:
            raise DecodeError('invalid style choice')
        rank = rank * radix + digit
    value = rank * (1 << (8 * size)) // scale
    data = value.to_bytes(size, 'big')
    if encode(data, radices) != digits:
        raise DecodeError('noncanonical arithmetic padding')
    return data
