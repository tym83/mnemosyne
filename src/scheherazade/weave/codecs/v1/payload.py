"""Versioned, bounded zlib/X25519/HKDF/ChaCha20-Poly1305 envelope.

Not age wire format; recipient encryption does not authenticate authorship.
The caller supplies canonical work bytes as context to bind unchanged music.
Keys are deliberately neither embedded nor persisted by this module.
"""
import hashlib
import os
import struct
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import DecodeError

MAGIC = b'SHW1'
LIMIT = 16 * 1024 * 1024
OVERHEAD = 72  # magic, length, ephemeral public key, nonce, AEAD tag, CRC32


def _key(shared, ephemeral, recipient):
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=ephemeral + recipient, info=MAGIC).derive(shared)


def seal(data: bytes, recipient: X25519PublicKey, *, context: bytes) -> bytes:
    if len(data) > LIMIT:
        raise ValueError('payload exceeds limit')
    compressed = zlib.compress(data, level=9)
    ephemeral = X25519PrivateKey.generate()
    public = ephemeral.public_key().public_bytes_raw()
    nonce = os.urandom(12)
    header = MAGIC + struct.pack('>I', len(compressed) + OVERHEAD) + public + nonce
    key = _key(ephemeral.exchange(recipient), public, recipient.public_bytes_raw())
    body = header + ChaCha20Poly1305(key).encrypt(
        nonce, compressed, header + hashlib.sha256(context).digest())
    return body + struct.pack('>I', zlib.crc32(body))


def open_envelope(frame: bytes, recipient: X25519PrivateKey, *, context: bytes) -> bytes:
    try:
        if not OVERHEAD <= len(frame) <= LIMIT + 65536:
            raise DecodeError('invalid frame size')
        if frame[:4] != MAGIC or struct.unpack('>I', frame[4:8])[0] != len(frame):
            raise DecodeError('invalid frame header/length')
        if struct.unpack('>I', frame[-4:])[0] != zlib.crc32(frame[:-4]):
            raise DecodeError('frame checksum mismatch')
        public = frame[8:40]
        key = _key(recipient.exchange(X25519PublicKey.from_public_bytes(public)),
                   public, recipient.public_key().public_bytes_raw())
        compressed = ChaCha20Poly1305(key).decrypt(
            frame[40:52], frame[52:-4], frame[:52] + hashlib.sha256(context).digest())
        inflater = zlib.decompressobj()
        data = inflater.decompress(compressed, LIMIT + 1)
        if len(data) > LIMIT or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise DecodeError('invalid or oversized compressed payload')
        return data
    except (InvalidTag, ValueError, zlib.error, struct.error) as exc:
        raise DecodeError('envelope rejected') from exc
