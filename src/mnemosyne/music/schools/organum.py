"""Notre-Dame organum: a chant tenor in long notes under upper voices in rhythmic modes."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .chant import MODES, WHITE, degree_pitch, place_final, walk, tenor_and_uppers
from .material import mark

PERFECTION = 1.5  # three eighths: one long-short unit of a ternary rhythmic mode
# Rhythmic modes as values within perfections (quarters): I long-short, II short-long,
# III long-short-short over two perfections, VI three shorts.
RHYTHMIC_MODES = {1: (1, .5), 2: (.5, 1), 3: (1.5, .5, 1), 6: (.5, .5, .5)}
PERFECT = (0, 7)  # unison, fifth, octave, twelfth... above the tenor (pitch-class distance)


def purum(sec):
    return sec['character'] != 'agitated' and sec['density'] < .75


def tenor_line(rng, start, end, sec, lo, hi):
    """Chant notes held for 4-8 perfections (organum purum) or mode-V longs (discant)."""
    events, at = [], start
    degrees = walk(rng, 64, lo, hi)
    k = 0
    while at < end:
        if purum(sec):
            length = PERFECTION*rng.randrange(4, 9)
        else:
            length = PERFECTION if k % 4 != 3 else PERFECTION*2
        length = min(length, end-at)
        if end-at-length < PERFECTION:
            length = end-at
        events.append((at, length, degrees[k % len(degrees)]))
        at += length
        k += 1
    return events


def consonant(tenor, previous, low, high, rng):
    candidates = [p for p in range(max(low, tenor), high+1)
                  if p % 12 in WHITE and (p-tenor) % 12 in PERFECT]
    if not candidates:
        candidates = [p for p in range(low, high+1) if p % 12 in WHITE and (p-tenor) % 12 in PERFECT]
    ranked = sorted(candidates, key=lambda p: (abs(p-previous), p))
    return ranked[0] if len(ranked) == 1 or rng.random() < .7 else ranked[1]


def step(pitch, direction, low, high):
    """Neighbouring white-key step; reflects at the edge of the register."""
    for d in (direction, -direction):
        p = pitch+d
        while p % 12 not in WHITE:
            p += d
        if low <= p <= high:
            return p
    return pitch


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'organum', choices=choices)
    mode = MODES[rng.randrange(8)]
    names = ENSEMBLES[plan['ensemble']]
    tenors, uppers = tenor_and_uppers(names)
    lines = min(3, len(uppers))
    for start, end, sec in sections:
        low, high = limits(names[tenors[0]], sec)
        final, lo, hi = place_final(mode['final'], *mode['ambitus'], low, high)
        held = tenor_line(rng, start, end, sec, lo, hi)
        style = 'organum purum' if purum(sec) else 'discant clausula'
        for i in tenors:
            mark(score.parts[i], start, f"Tenor: chant in mode {mode['number']}; {style}")
            for at, length, degree in held:
                put(score.parts[i], at, length, degree_pitch(final, degree))
        for k, i in enumerate(uppers):
            line = k % lines
            rmode = rng.choice([1, 6] if line == 0 and lines > 1 else [1, 2] if line == 1 else [1, 3])
            plow, phigh = limits(names[i], sec)
            name = ('quadruplum', 'triplum', 'duplum')[3-lines+line]
            mark(score.parts[i], start, f'{name}: rhythmic mode {rmode}')
            previous = (plow+phigh)//2
            at, ordo = start, 0
            pattern = RHYTHMIC_MODES[rmode]
            span = sum(pattern)
            ordo_length = rng.randrange(2, 5)
            while at+span <= end:
                tenor_pitch = next(degree_pitch(final, d) for a, l, d in held if a <= at < a+l)
                ordo += 1
                closing = ordo % ordo_length == 0
                cursor = at
                for j, value in enumerate(pattern):
                    if j == 0:
                        pitch = consonant(tenor_pitch, previous, plow, phigh, rng)
                    elif rmode == 3 and j == 1 and cursor-at >= PERFECTION:
                        # Second perfection of mode III also begins on a concord.
                        here = next(degree_pitch(final, d) for a, l, d in held if a <= cursor < a+l)
                        pitch = consonant(here, previous, plow, phigh, rng)
                    else:
                        pitch = step(previous, rng.choice([-1, 1]), plow, phigh)
                    if closing and j == len(pattern)-1:
                        cursor += value  # ordo ends with a rest in place of its last value
                        break
                    put(score.parts[i], cursor, value, pitch)
                    previous = pitch
                    cursor += value
                at += span
            if at < end:
                put(score.parts[i], at, end-at, consonant(degree_pitch(final, held[-1][2]), previous, plow, phigh, rng))
    score.editorial.mode = mode
    score.editorial.tenor_parts = tenors
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Chant tenor, rhythmic modes and concords remain fixed; the swell of held tenor notes is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
