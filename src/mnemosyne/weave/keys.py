"""Two keys: the owner reads, the atelier writes.

The owner's X25519 private key never enters the cluster. The atelier holds
only the owner's public key (to seal snapshots it cannot open) and its own
X25519 private key. Frames, catalogues and carriers are authenticated with a
secret both sides can derive and nobody else can: the X25519 agreement of the
atelier key with the owner key. The atelier's public key travels in every
work's metadata; it is not secret.

Both classes are drop-in for the earlier single private key: codecs call
public_key() to seal, private_bytes_raw() for the authentication secret, and
restore calls exchange() to open envelopes (only the owner can).
"""
import hashlib

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

DOMAIN = b'mnemosyne/atelier-authentication/v1\0'


def agreement(private: X25519PrivateKey, public: X25519PublicKey) -> bytes:
    return hashlib.sha256(DOMAIN + private.exchange(public)).digest()


def public_hex(key) -> str:
    return key.public_bytes_raw().hex()


class WritingKey:
    """What the atelier holds: its own key and the owner's public key."""
    def __init__(self, atelier: X25519PrivateKey, owner: X25519PublicKey):
        self.atelier, self.owner = atelier, owner
        self.secret = agreement(atelier, owner)

    def public_key(self):
        return self.owner

    def private_bytes_raw(self):
        return self.secret

    def atelier_public(self) -> str:
        return public_hex(self.atelier.public_key())

    def exchange(self, _):
        raise PermissionError('the atelier cannot open its own snapshots')


class ReadingKey:
    """What the owner holds at restore: the owner key and a work's atelier public key."""
    def __init__(self, owner: X25519PrivateKey, atelier: X25519PublicKey):
        self.owner, self.atelier = owner, atelier
        self.secret = agreement(owner, atelier)

    def public_key(self):
        return self.owner.public_key()

    def private_bytes_raw(self):
        return self.secret

    def exchange(self, peer):
        return self.owner.exchange(peer)

    def atelier_public(self) -> str:
        return public_hex(self.atelier)


def reading(owner: X25519PrivateKey, atelier_hex: str | None):
    """The key a work was written with: split keys, or the legacy single key."""
    if not atelier_hex:
        return owner
    return ReadingKey(owner, X25519PublicKey.from_public_bytes(bytes.fromhex(atelier_hex)))
