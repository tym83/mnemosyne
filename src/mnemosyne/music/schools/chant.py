"""Shared modal material for the chant-based schools: church modes and voice roles."""
from .common import RANGES

WHITE = (0, 2, 4, 5, 7, 9, 11)
# Eight church modes: final, reciting tone (tenor) and ambitus in diatonic steps
# relative to the final. Authentic modes span final..octave (one step below
# allowed), plagal modes a fourth below to a sixth above the final.
MODES = (
    {'number': 1, 'name': 'Dorian', 'final': 2, 'tenor': 9, 'ambitus': (-1, 8)},
    {'number': 2, 'name': 'Hypodorian', 'final': 2, 'tenor': 5, 'ambitus': (-3, 5)},
    {'number': 3, 'name': 'Phrygian', 'final': 4, 'tenor': 0, 'ambitus': (-1, 8)},
    {'number': 4, 'name': 'Hypophrygian', 'final': 4, 'tenor': 9, 'ambitus': (-3, 5)},
    {'number': 5, 'name': 'Lydian', 'final': 5, 'tenor': 0, 'ambitus': (-1, 8)},
    {'number': 6, 'name': 'Hypolydian', 'final': 5, 'tenor': 9, 'ambitus': (-3, 5)},
    {'number': 7, 'name': 'Mixolydian', 'final': 7, 'tenor': 2, 'ambitus': (-1, 8)},
    {'number': 8, 'name': 'Hypomixolydian', 'final': 7, 'tenor': 0, 'ambitus': (-3, 5)},
)


def degree_pitch(final_pitch, degree):
    """Diatonic (white-key) pitch `degree` steps from a white-key final."""
    octave, step = divmod(WHITE.index(final_pitch % 12)+degree, 7)
    return final_pitch - final_pitch % 12 + 12*octave + WHITE[step]


def pitch_degree(final_pitch, pitch):
    """Inverse of degree_pitch; None for a pitch outside the white-key gamut."""
    octave, pc = divmod(pitch - (final_pitch - final_pitch % 12), 12)
    return 7*octave + WHITE.index(pc) - WHITE.index(final_pitch % 12) if pc in WHITE else None


def place_final(final_pc, low_degree, high_degree, low, high):
    """Final pitch whose ambitus best fits [low, high]; returns (final, lo, hi) degrees that fit."""
    best = None
    for final in range(final_pc, 128, 12):
        lo = next((d for d in range(low_degree, high_degree+1) if degree_pitch(final, d) >= low), None)
        hi = next((d for d in range(high_degree, low_degree-1, -1) if degree_pitch(final, d) <= high), None)
        if lo is None or hi is None or lo > 0 or hi < 0:
            continue
        span = hi-lo
        if best is None or span > best[0]:
            best = (span, final, lo, hi)
    if best is None:
        raise ValueError('register cannot hold the mode final')
    return best[1:]


def walk(rng, length, lo, hi, start=0, end=0, step_bias=.8):
    """Mostly stepwise degree walk inside [lo, hi] that closes on `end`."""
    degrees, d = [], start
    for k in range(length):
        remaining = length-1-k
        if remaining == 0:
            d = end
        elif abs(d-end) >= remaining:
            d += 1 if end > d else -1
        else:
            move = rng.choice([-1, 1]) * (1 if rng.random() < step_bias else 2)
            d = max(lo, min(hi, d+move))
        degrees.append(d)
    return degrees


def tenor_and_uppers(names):
    """Lowest non-piano part(s) carry the tenor; the rest are upper voices, highest first."""
    candidates = [i for i, n in enumerate(names) if n != 'piano'] or [len(names)-1]
    lowest = min(RANGES[names[i]][0] for i in candidates)
    tenor = [i for i in candidates if RANGES[names[i]][0] == lowest]
    uppers = sorted((i for i in range(len(names)) if i not in tenor),
                    key=lambda i: (-(RANGES[names[i]][0]+RANGES[names[i]][1]), i))
    return tenor, uppers
