"""Viennese periods: antecedent/consequent over functional harmony, Alberti bass, a trip to the dominant."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark
from .tonal import chord, scale, nearest, step, roles, band

SLOT = 2  # one harmony per half bar
ANTECEDENT = (('I', 'I', 'IV', 'I', 'ii', 'V', 'V', 'V'),
              ('I', 'V', 'I', 'IV', 'I', 'ii', 'V', 'V'),
              ('I', 'I', 'vi', 'IV', 'ii', 'ii', 'V', 'V'))
CLOSE = ('ii', 'V7', 'I', 'I')          # perfect authentic cadence
MODULATE = ('ii', 'V7', 'I', 'I')       # the same cadence, sounding in the dominant key
RETURN = ('IV', 'ii', 'V7', 'V7')       # standing on the home dominant
RHYTHMS = ((1, 1, 1, 1), (1.5, .5, 1, 1), (2, 1, 1), (.5, .5, 1, 2), (1, .5, .5, 1, 1), (1, 1, 2))


def plan_phrases(sections, rng):
    """(start, slots[(numeral, key)], kind) for every phrase; codettas fill odd bars."""
    phrases = []
    n = len(sections)
    for s, (start, end, sec) in enumerate(sections):
        key = 7 if 0 < s < n-1 else 0
        bars = int((end-start)//4)
        count = bars//4
        at = start
        for p in range(count):
            template = ANTECEDENT[rng.randrange(len(ANTECEDENT))] if p % 2 == 0 else template
            last = p == count-1
            if p % 2 == 0 and not last:
                slots, kind = [(c, key) for c in template], 'half'
            elif last and s == 0 and n >= 3:
                slots, kind = [(c, 0) for c in template[:4]] + [(c, 7) for c in MODULATE], 'modulating'
            elif last and key == 7 and s == n-2:
                slots, kind = [(c, 7) for c in template[:4]] + [(c, 0) for c in RETURN], 'retransition'
            else:
                slots, kind = [(c, key) for c in template[:4]+CLOSE], 'full'
            phrases.append((at, slots, kind, p % 2 == 1))
            at += 16
        while at+4 <= end:
            if key == 7 and s == n-2:
                slots = [('V7', 0), ('V7', 0)]  # keep standing on the home dominant
            elif at+8 <= end:
                slots = [('I', key), ('V7', key)]
            else:
                slots = [('I', key), ('I', key)]
            phrases.append((at, slots, 'codetta', False))
            at += 4
        if at < end:
            phrases.append((at, [('I', key)], 'tail', False))
    return phrases


def harmony_at(phrases, at):
    for start, slots, kind, _ in reversed(phrases):
        if start <= at:
            index = min(int((at-start)//SLOT), len(slots)-1)
            return slots[index]
    return phrases[0][1][0]


def melody(rng, phrases, tonic, low, high, ends):
    notes = []
    previous = (low+high)//2
    opening = None
    for start, slots, kind, consequent in phrases:
        length = len(slots)*SLOT if kind != 'tail' else ends(start)-start
        if kind in ('codetta', 'tail'):
            numeral, key = slots[0]
            pitch = nearest(chord(tonic, numeral, key)[:1], previous, low, high)
            notes.append((start, min(2, length), pitch))
            previous = pitch
            continue
        rhythm = [rng.choice(RHYTHMS) for _ in range(3)]
        if consequent and opening:
            notes += [(start+a-opening[0][0], l, p) for a, l, p in opening]
            at = start+8
            previous = opening[-1][2]
            bars = rhythm[2:]
        else:
            at = start
            bars = rhythm
            first = []
        for bar in bars:
            for value in bar:
                numeral, key = harmony_at(phrases, at)
                pcs = chord(tonic, numeral, key)
                if (at-start) % 2 == 0:
                    pitch = nearest(pcs, previous+rng.choice([-3, -1, 1, 3]), low, high)
                else:
                    pitch = step(previous, scale(tonic, key=key), rng.choice([-1, 1]), low, high)
                notes.append((at, value, pitch))
                if not consequent and at < start+8:
                    first.append((at, value, pitch))
                previous = pitch
                at += value
        numeral, key = slots[-1]
        if kind == 'half':
            target = [(tonic+key+2) % 12, (tonic+key+7) % 12]
            opening = first
        else:
            target = [chord(tonic, numeral, key)[0]]
        cadence = nearest(target, previous, low, high)
        notes.append((start+12, 2, cadence))
        previous = cadence
    return notes


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'classical', choices=choices)
    tonic = int(plan.get('tonic', 60)) % 12
    names = ENSEMBLES[plan['ensemble']]
    role = roles(names)
    phrases = plan_phrases(sections, rng)
    ends = {}
    for (start, _, _, _), nxt in zip(phrases, phrases[1:]+[(total,)]):
        ends[start] = nxt[0]

    def section_of(at):
        return next(sec for a, b, sec in sections if a <= at < b)

    for i, (part, name) in enumerate(zip(score.parts, names)):
        r = role[i]
        for a, b, sec in sections:
            key = harmony_at(phrases, a)[1]
            mark(part, a, f"{r}; {'dominant' if key else 'home'} key")
        if r == 'melody':
            low, high = limits(name, sections[0][2])
            top = min(high, max(low+12, 84))
            for at, length, pitch in melody(rng, phrases, tonic, max(low, top-16), top, ends.__getitem__):
                lo, hi = limits(name, section_of(at))
                while pitch > hi:
                    pitch -= 12
                while pitch < lo:
                    pitch += 12
                put(part, at, length, pitch)
            continue
        previous = None
        for start, slots, kind, _ in phrases:
            for k, (numeral, key) in enumerate(slots):
                at = start+k*SLOT
                span = min(SLOT, ends[start]-at) if kind != 'tail' else ends[start]-at
                if span <= 0:
                    continue
                sec = section_of(at)
                low, high = limits(name, sec)
                pcs = chord(tonic, numeral, key)
                if r == 'bass' and name != 'piano':
                    root = nearest(pcs[:1], low+7, low, high)
                    value = 1 if sec['density'] >= .7 else span
                    for t in range(int(span//value)):
                        put(part, at+t*value, value, root)
                elif r in ('bass', 'keys'):
                    lo, hi = band(low, high, 50 if r == 'bass' else 62, 19)
                    root = nearest(pcs[:1], lo+4, lo, hi)
                    fifth = nearest(pcs[2:3] if len(pcs) < 4 else pcs[3:4], root+7, lo, hi)
                    third = nearest(pcs[1:2], root+4, lo, hi)
                    figure = (root, fifth, third, fifth)
                    for t in range(int(span/.5)):
                        put(part, at+t*.5, .5, figure[t % 4])
                else:
                    lo, hi = band(low, high, 64, 14)
                    rank = sum(1 for j in range(i) if role[j] == 'inner')
                    target = previous if previous is not None else lo+3*(rank % 4)
                    pitch = nearest([pcs[(rank+1) % len(pcs)], pcs[(rank+2) % len(pcs)]], target, lo, hi)
                    previous = pitch
                    value = .5 if sec['density'] >= .6 else 1
                    for t in range(int(span//value)):
                        put(part, at+t*value, value*.75 if value == 1 else value, pitch)
    score.editorial.cadences = [(start, slots[-1], kind) for start, slots, kind, _ in phrases
                                if kind in ('half', 'full', 'modulating', 'retransition')]
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Periods, harmony and cadences remain fixed; phrasing and touch within each level are free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
