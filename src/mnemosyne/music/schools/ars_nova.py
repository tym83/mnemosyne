"""Isorhythmic motet: talea x color tenor, faster upper voices, hocket, double-leading-tone cadences."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .chant import WHITE, degree_pitch, place_final, walk, tenor_and_uppers
from .material import mark

CADENCE = 3  # quarters reserved for the closing double-leading-tone cadence
# Upper-voice intervals above the final: penultimate -> final (semitones).
CLOSE = {'triplum': (11, 12), 'motetus': (6, 7), 'contratenor': (9, 7)}
PERFECT, IMPERFECT = (0, 7), (3, 4, 8, 9)
ROLES = ('triplum', 'motetus', 'contratenor')


def talea_and_color(rng, lo, hi):
    """A rhythm (talea, one closing rest) and a pitch series (color) of a different length."""
    size = rng.randrange(4, 7)
    talea = [(rng.choice([1, 1.5, 2, 3]), False) for _ in range(size-1)] + [(rng.choice([1, 1.5]), True)]
    notes = size-1
    length = rng.randrange(notes+2, 2*notes+3)
    if length % notes == 0:
        length += 1
    color = walk(rng, length, lo, hi, start=0, end=1)
    return talea, color


def sounding(events, at):
    return next((p for a, l, p in events if a <= at < a+l and p is not None), None)


def chosen(tenor, previous, low, high, rng, strong):
    allowed = PERFECT if strong else PERFECT+IMPERFECT
    pool = [p for p in range(low, high+1) if (p % 12 in WHITE)
            and (tenor is None or (p-tenor) % 12 in allowed)]
    pool = sorted(pool, key=lambda p: (abs(p-previous), p))
    return pool[0] if len(pool) == 1 or rng.random() < .65 else pool[1]


def step(pitch, low, high, rng):
    d = rng.choice([-1, 1])
    for direction in (d, -d):
        p = pitch+direction
        while p % 12 not in WHITE:
            p += direction
        if low <= p <= high:
            return p
    return pitch


def placed(final, interval, low, high):
    """Octave placement of a cadence pair (penultimate, final) nearest the middle of the range."""
    a, b = interval
    fits = [final+o for o in range(-48, 49, 12) if low <= final+o+min(a, b) and final+o+max(a, b) <= high]
    base = min(fits, key=lambda f: (abs(f+b-(low+high)/2), f))
    return base+a, base+b


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'ars_nova', choices=choices)
    names = ENSEMBLES[plan['ensemble']]
    tenors, uppers = tenor_and_uppers(names)
    final_pc = rng.choice([2, 7, 5, 0])
    tlow, thigh = limits(names[tenors[0]], sections[0][2])
    final, lo, hi = place_final(final_pc, -2, 6, tlow, thigh)
    talea, color = talea_and_color(rng, max(lo, -2), min(hi, 6))
    c_index = 0
    for start, end, sec in sections:
        low, high = limits(names[tenors[0]], sec)
        fin, slo, shi = place_final(final_pc, -2, 6, low, high)
        diminution = .5 if sec['character'] == 'agitated' else 1
        hocket = sec['density'] >= .75
        events, at = [], start
        body = end-CADENCE
        span = sum(v for v, _ in talea)*diminution
        while at+span <= body:
            for value, rest in talea:
                value *= diminution
                if rest:
                    events.append((at, value, None))
                else:
                    degree = max(slo, min(shi, color[c_index % len(color)]))
                    events.append((at, value, degree_pitch(fin, degree)))
                    c_index += 1
                at += value
        events.append((at, body-at, None))
        events += [(body, 1, degree_pitch(fin, 1)), (body+1, CADENCE-1, fin)]
        for i in tenors:
            mark(score.parts[i], start, 'Tenor: talea x color' + (', diminution' if diminution < 1 else ''))
            for a, length, pitch in events:
                if pitch is not None:
                    put(score.parts[i], a, length, pitch)
        for rank, i in enumerate(uppers):
            role = ROLES[rank] if rank < 3 else ROLES[rank % 2]
            plow, phigh = limits(names[i], sec)
            mark(score.parts[i], start, role + ('; hocket' if hocket and role != 'contratenor' else ''))
            previous = (plow+phigh)//2
            if role == 'contratenor':
                # Isorhythmic too: the tenor's rhythm with its own concords above.
                for a, length, pitch in events[:-2]:
                    if pitch is not None:
                        previous = chosen(pitch, previous, plow, phigh, rng, False)
                        put(score.parts[i], a, length, previous)
            elif hocket:
                parity = 0 if role == 'triplum' else 1
                cell = .5
                k, at = 0, start
                while at+cell <= body:
                    if k % 2 == parity:
                        previous = chosen(sounding(events, at), previous, plow, phigh, rng, True)
                        put(score.parts[i], at, cell, previous)
                    k += 1
                    at += cell
            else:
                values = (.25, .5, .5, .75, 1) if role == 'triplum' else (.5, 1, 1, 1.5)
                at = start
                onsets = {a for a, _, p in events if p is not None}
                while at < body:
                    value = min(rng.choice(values), body-at)
                    tenor = sounding(events, at)
                    strong = at in onsets
                    if strong or rng.random() < .3:
                        previous = chosen(tenor, previous, plow, phigh, rng, strong)
                    else:
                        previous = step(previous, plow, phigh, rng)
                    put(score.parts[i], at, value, previous)
                    at += value
            penult, last = placed(fin, CLOSE[role], plow, phigh)
            put(score.parts[i], body, 1, penult)
            put(score.parts[i], body+1, CADENCE-1, last)
    score.editorial.talea = talea
    score.editorial.color = color
    score.editorial.tenor_parts = tenors
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Talea, color, hocket and cadences remain fixed; the weight of each note is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
