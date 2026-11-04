"""Literature carrier boundary for the growing Lives.

There is no literature codec yet: actual capacity is ZERO bytes. A future
codec must report verified bytes per rendered passage, not tokens or guessed
entropy. Planning estimate only: 1 bit per independently reversible binary
choice (800 choices = 100 gross bytes, 80 bytes after frame overhead).
A compressed encrypted payload adds 72 bytes; each frame adds 20 bytes.
Until an audited encode/decode channel exists, text and chapters are ordinary
Atelier state, never advertised as an embedded recoverable backup.
"""
from . import frames, payload


def capacity(verified_bits: int = 0) -> dict:
    if verified_bits < 0:
        raise ValueError('negative capacity')
    gross = verified_bits // 8
    return {'gross_bytes': gross, 'payload_bytes_per_frame': max(0, gross - frames.OVERHEAD),
            'envelope_overhead': payload.OVERHEAD, 'channel_available': False}


def frame_payload(data: bytes, key, contexts: list[bytes], verified_bytes: int) -> list[bytes]:
    """Hook for a future literature codec; contexts are canonical passage bytes.

    Uses exactly the shared payload envelope and authenticated multipart frames.
    This prepares frames, not steganographic text. No key is stored in Lives.
    """
    if verified_bytes <= frames.OVERHEAD:
        raise ValueError('literature channel has no verified capacity')
    envelope = payload.seal(data, key.public_key(), context=frames.DOMAIN)
    count = (len(envelope) + verified_bytes - frames.OVERHEAD - 1) // (verified_bytes - frames.OVERHEAD)
    if len(contexts) != count:
        raise ValueError(f'need {count} canonical passage contexts')
    return [frames.pack(envelope, i, verified_bytes, key, context) for i, context in enumerate(contexts)]
