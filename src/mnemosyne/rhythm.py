"""A creator's own rhythm: whether they sit down to work on a given day of the atelier's life.

The atelier lives without pause; it is the creator who works or not, moved by their fertility and
drive. Illness, despair, silence and renunciation already take them out of `Lineage.working()`.
"""
import hashlib
import random

# Mean days between a creator's working days, before fertility and drive move it.
EVERY = {'music': 45., 'literature': 28.}


def works_today(artist, day, seed=0, every=None):
    every = every if every is not None else EVERY.get(artist.art, 30.)
    r = random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{day}:{artist.id}'.encode()).digest()[:8], 'big'))
    return r.random() < (1 / max(1., every)) * max(.3, 1 + artist.fertility) * (.5 + artist.drive)
