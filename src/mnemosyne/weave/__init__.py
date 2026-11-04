"""Deterministic art channels. A transport round trip is not an opus proof."""


class DecodeError(ValueError):
    """Untrusted or damaged input; no recovered payload may be published."""
