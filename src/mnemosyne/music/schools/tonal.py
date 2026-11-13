"""Shared tonal material for the common-practice schools: keys, chords and ensemble roles."""
from .common import RANGES

MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)
HARMONIC_MINOR = (0, 2, 3, 5, 7, 8, 11)
QUALITIES = {'maj': (0, 4, 7), 'min': (0, 3, 7), 'dim': (0, 3, 6), 'aug': (0, 4, 8),
             'dom7': (0, 4, 7, 10), 'dim7': (0, 3, 6, 9), 'min7': (0, 3, 7, 10), 'hdim7': (0, 3, 6, 10)}
# Roman numerals relative to a local tonic: (root offset, quality).
DEGREES = {'I': (0, 'maj'), 'ii': (2, 'min'), 'iii': (4, 'min'), 'IV': (5, 'maj'), 'V': (7, 'maj'),
           'V7': (7, 'dom7'), 'vi': (9, 'min'), 'viio': (11, 'dim'),
           'i': (0, 'min'), 'iio': (2, 'dim'), 'III': (3, 'maj'), 'iv': (5, 'min'), 'VI': (8, 'maj'),
           'VII': (10, 'maj'), 'bIII': (3, 'maj'), 'bVI': (8, 'maj'), 'N': (1, 'maj'),
           'III#': (4, 'maj'), 'VI#': (9, 'maj'), 'ii7': (2, 'min7'), 'IV7': (5, 'maj')}


def chord(tonic, numeral, key=0):
    """Pitch classes of a numeral in the key `key` semitones above `tonic`; root first."""
    if '/' in numeral:
        # Applied chords: V7/x or viio7/x of the degree x.
        head, target = numeral.split('/')
        base = (tonic+key+DEGREES[target][0]) % 12
        root, quality = ((base+7) % 12, 'dom7') if head == 'V7' else ((base+11) % 12, 'dim7')
    else:
        offset, quality = DEGREES[numeral]
        root = (tonic+key+offset) % 12
    return [(root+x) % 12 for x in QUALITIES[quality]]


def scale(tonic, minor=False, key=0):
    return {(tonic+key+x) % 12 for x in (HARMONIC_MINOR if minor else MAJOR)}


def nearest(pcs, target, low, high):
    """Playable pitch nearest `target` whose pitch class is in `pcs`."""
    pool = [p for p in range(low, high+1) if p % 12 in pcs]
    return min(pool, key=lambda p: (abs(p-target), p))


def step(pitch, pcs, direction, low, high):
    """Next scale tone in `direction`, reflected at the range boundary."""
    for d in (direction, -direction):
        p = pitch+d
        while low <= p <= high and p % 12 not in pcs:
            p += d
        if low <= p <= high:
            return p
    return pitch


def roles(names):
    """melody / bass / keys / inner for a version-2 ensemble."""
    n = len(names)
    melody = [i for i in range(max(1, n//4)) if names[i] == names[0]]
    candidates = [i for i in range(n) if names[i] != 'piano' and i not in melody]
    if candidates:
        lowest = min(RANGES[names[i]][0] for i in candidates)
        bass = [i for i in candidates if RANGES[names[i]][0] == lowest]
    else:
        bass = [n-1]
    out = {}
    for i, name in enumerate(names):
        out[i] = ('melody' if i in melody else 'bass' if i in bass
                  else 'keys' if name == 'piano' else 'inner')
    return out


def band(low, high, centre, width):
    """A sub-range of `width` semitones around `centre`, kept inside [low, high]."""
    lo = max(low, min(high-width, round(centre-width/2)))
    return lo, min(high, lo+width)
