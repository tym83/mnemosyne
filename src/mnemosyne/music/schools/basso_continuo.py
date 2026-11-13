"""Baroque continuo: a bass on every beat, realized chords, ritornello and circle-of-fifths episodes."""
from music21 import dynamics, stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark
from .tonal import MAJOR, HARMONIC_MINOR, chord, nearest, roles, band

SLOT = 2
UNIT = 16  # four bars: one ritornello statement or one episode
RITORNELLO = {False: ('I', 'IV', 'V', 'I', 'vi', 'ii', 'V', 'I'),
              True: ('i', 'iv', 'V', 'i', 'VI', 'iio', 'V', 'i')}
# Diatonic circle of fifths: every root a fifth below the last.
CIRCLE = {False: ('I', 'IV', 'viio', 'iii', 'vi', 'ii'), True: ('i', 'iv', 'VII', 'III', 'VI', 'iio')}
CELLS = ((.5, .5, .5, .5), (.25, .25, .25, .25, 1), (1, .5, .5), (.5, .25, .25, .5, .5), (.25, .25, .5, 1))


def timeline(total, minor):
    """Alternating four-bar ritornello and episode units; keys visit V and IV and return home."""
    count = int(total // UNIT)
    kinds = ['ritornello' if u % 2 == 0 or u == count-1 else 'episode' for u in range(count)]
    middle = (7, 5, 2) if not minor else (7, 5, 10)
    rit = [u for u, kind in enumerate(kinds) if kind == 'ritornello']
    keys = {u: 0 if j in (0, len(rit)-1) else middle[(j-1) % len(middle)] for j, u in enumerate(rit)}
    units, slots = [], []
    for u, kind in enumerate(kinds):
        start = u*UNIT
        if kind == 'ritornello':
            key = keys[u]
            harmony = [(c, key) for c in RITORNELLO[minor]]
        else:
            key = keys[u-1]
            following = keys[next(v for v in rit if v > u)]
            # Six links of the circle of fifths, then the dominant of the next ritornello's key.
            harmony = [(c, key) for c in CIRCLE[minor]] + [('V7', following)]*2
        units.append((start, kind, key))
        slots += [(start+k*SLOT, c, kk, kind) for k, (c, kk) in enumerate(harmony)]
    return units, slots, count*UNIT


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'basso_continuo', choices=choices)
    tonic = int(plan.get('tonic', 60)) % 12
    minor = rng.random() < .4
    names = ENSEMBLES[plan['ensemble']]
    role = roles(names)
    units, slots, body = timeline(float(total), minor)
    scale_pcs = lambda key: {(tonic+key+x) % 12 for x in (HARMONIC_MINOR if minor else MAJOR)}

    def section_of(at):
        return next(sec for a, b, sec in sections if a <= at < b)

    # Terraced dynamics replace the section levels: forte tutti, piano solo.
    for part in score.parts:
        for d in list(part.getElementsByClass(dynamics.Dynamic)):
            part.remove(d)
        for start, kind, _ in units:
            mark(part, start, 'tutti' if kind == 'ritornello' else 'solo', 'f' if kind == 'ritornello' else 'p')
        if body < total:
            mark(part, body, 'tutti', 'f')
    melody_figure = [rng.choice(CELLS) for _ in range(8)]
    sequence_cell = rng.choice(CELLS[:2]+CELLS[3:])
    sequence_shape = [rng.choice([-1, 1, 2]) for _ in sequence_cell]
    for i, (part, name) in enumerate(zip(score.parts, names)):
        r = role[i]
        solo = r == 'melody' and i == 0
        previous = None
        for k, (at, numeral, key, kind) in enumerate(slots):
            sec = section_of(at)
            low, high = limits(name, sec)
            pcs = chord(tonic, numeral, key)
            nxt = chord(tonic, *slots[k+1][1:3]) if k+1 < len(slots) else pcs
            if r == 'bass':
                lo, hi = band(low, high, low+12, 17)
                root = nearest(pcs[:1], previous if previous is not None else lo+5, lo, hi)
                target = nearest(nxt[:1], root, lo, hi)
                between = [p for p in range(min(root, target)+1, max(root, target)) if p % 12 in scale_pcs(key)]
                passing = between[len(between)//2] if between else nearest(pcs[1:3], root+3, lo, hi)
                if name == 'piano':
                    # A keyboard bass part realizes the figures itself: chord above the bass note.
                    clo, chi = band(low, high, 62, 14)
                    put(part, at, 1, [root]+sorted({nearest([pc], clo+4+3*j, clo, chi) for j, pc in enumerate(pcs[:3])} - {root}))
                else:
                    put(part, at, 1, root)
                put(part, at+1, 1, passing)  # the bass moves on every beat
                previous = target
            elif r == 'keys':
                lo, hi = band(low, high, 64, 14)
                upper = sorted(nearest([pc], previous[j] if previous else lo+4+3*j, lo, hi) for j, pc in enumerate(pcs[:3]))
                blo, bhi = band(low, high, 43, 14)
                bass = nearest(pcs[:1], blo+5, blo, bhi)
                previous = upper
                for beat in range(2):
                    put(part, at+beat, .75, [bass]+upper)
            elif r == 'melody':
                if kind == 'episode' and not solo:
                    continue
                lo, hi = band(low, high, 76, 16)
                cell = sequence_cell if kind == 'episode' else melody_figure[(k % 8)]
                start_pitch = nearest(pcs, previous if previous is not None else (lo+hi)//2, lo, hi)
                pitch, t = start_pitch, at
                key_pcs = scale_pcs(key) | set(pcs)
                for j, value in enumerate(cell):
                    put(part, t, value, pitch)
                    t += value
                    move = sequence_shape[j % len(sequence_shape)] if kind == 'episode' else rng.choice([-1, 1, 2, -2])
                    candidates = [p for p in range(lo, hi+1) if p % 12 in key_pcs]
                    idx = min(range(len(candidates)), key=lambda q: abs(candidates[q]-pitch))
                    pitch = candidates[max(0, min(len(candidates)-1, idx+move))]
                previous = start_pitch
            else:
                if kind == 'episode':
                    continue
                lo, hi = band(low, high, 64, 14)
                rank = sum(1 for j in range(i) if role[j] == 'inner')
                pitch = nearest([pcs[(rank+1) % len(pcs)], pcs[(rank+2) % len(pcs)]], previous or lo+4, lo, hi)
                previous = pitch
                put(part, at, SLOT, pitch)
        # Closing cadence on the home tonic after the last full unit.
        if body < total:
            low, high = limits(name, section_of(body))
            pcs = chord(tonic, 'i' if minor else 'I')
            pitch = nearest(pcs[:1] if r in ('bass', 'melody') else pcs[1:2], (low+high)//2 if r != 'bass' else low+7, low, high)
            put(part, body, total-body, pitch)
    score.editorial.slots = slots
    score.editorial.units = units
    score.editorial.minor = minor
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Bass, realization, ritornello and sequences remain fixed; touch within each terrace is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
