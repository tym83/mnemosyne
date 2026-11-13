"""Romantic song without words: long melody over wide arpeggios, chromatic harmony, swells to one climax."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark
from .tonal import QUALITIES, DEGREES, chord, scale, nearest, step, roles, band

SLOT = 2
SKELETONS = {False: (('vi', 'IV'), ('iii', 'IV'), ('IV', 'ii'), ('bVI', 'IV'), ('III#', 'vi'), ('vi', 'ii')),
             True: (('VI', 'iv'), ('III', 'iv'), ('iv', 'N'), ('VI', 'III'), ('iv', 'VI'))}
RHYTHMS = ((2, 1, 1), (3, 1), (1.5, .5, 2), (2, 2), (1, 1, 2), (2, 1.5, .5))
LEVELS = ('ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff')


def phrase_slots(rng, minor, key, full):
    tonic = 'i' if minor else 'I'
    x, y = rng.choice(SKELETONS[minor])
    applied = rng.choice(['V7/', 'viio7/'])
    slots = [tonic, tonic, applied+x, x]
    if full:
        slots += [y if rng.random() < .5 else rng.choice(['V7/', 'viio7/'])+y, 'V7', tonic, tonic]
    else:
        slots += [y, y, 'viio7/V', 'V']
    return [(s, key, minor) for s in slots]


def plan_phrases(rng, sections, minor):
    phrases = []
    n = len(sections)
    for s, (start, end, sec) in enumerate(sections):
        middle = 0 < s < n-1
        key, mode = (8, False) if middle else (0, minor)
        at, p = start, 0
        while at+16 <= end:
            full = p % 2 == 1 or at+32 > end
            phrases.append((at, phrase_slots(rng, mode, key, full), 'full' if full else 'half'))
            at += 16
            p += 1
        while at < end:
            tonic = 'i' if mode else 'I'
            phrases.append((at, [(tonic, key, mode)]*int(max(1, (end-at)//SLOT)), 'codetta'))
            at += max(SLOT, SLOT*((end-at)//SLOT))
    return phrases


def pcs(tonic, slot):
    numeral, key, _ = slot
    return chord(tonic, numeral, key)


def harmony_at(phrases, at):
    for start, slots, _ in reversed(phrases):
        if start <= at:
            return slots[min(int((at-start)//SLOT), len(slots)-1)]
    return phrases[0][1][0]


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'romantic', choices=choices)
    tonic = int(plan.get('tonic', 60)) % 12
    minor = rng.random() < .5
    names = ENSEMBLES[plan['ensemble']]
    role = roles(names)
    has_keys = any(n == 'piano' for n in names)
    arpeggio = {i for i, r in role.items() if (r in ('keys', 'bass') and names[i] == 'piano')
                or (not has_keys and names[i] == 'cello' and r in ('bass', 'inner'))}
    if not has_keys and any(names[i] == 'cello' and role[i] == 'inner' for i in role):
        arpeggio -= {i for i in arpeggio if role[i] == 'bass'}
    phrases = plan_phrases(rng, sections, minor)
    climax = float(total)*.62

    def intensity(at):
        return max(0., 1-abs(float(at)-climax)/max(climax, float(total)-climax))

    def section_of(at):
        return next(sec for a, b, sec in sections if a <= at < b)

    def ends(index):
        return phrases[index+1][0] if index+1 < len(phrases) else total

    # Swells: each phrase rises toward its middle and falls back; the climax rises furthest.
    for start, slots, kind in phrases:
        if kind == 'codetta' or start+14 > total:
            continue
        base = LEVELS.index(section_of(start).get('dynamic') or {'still': 'pp', 'flowing': 'p', 'agitated': 'f', 'luminous': 'mp', 'dissolving': 'ppp'}[section_of(start)['character']])
        peak = LEVELS[min(len(LEVELS)-1, base+1+round(2*intensity(start+8)))]
        for part in score.parts:
            mark(part, start+8, 'cresc.', peak)
            mark(part, start+14, 'dim.', LEVELS[base])
    for i, (part, name) in enumerate(zip(score.parts, names)):
        r = role[i]
        mark(part, 0, 'cantabile' if r == 'melody' else 'arpeggiando' if i in arpeggio else r)
        previous = None
        for index, (start, slots, kind) in enumerate(phrases):
            end = ends(index)
            if r == 'melody':
                previous = melody(rng, part, name, tonic, phrases, start, end, kind, slots, previous,
                                  section_of, intensity)
                continue
            for k, slot in enumerate(slots):
                at = start+k*SLOT
                span = min(SLOT, end-at) if k < len(slots)-1 else end-at
                if span <= 0:
                    continue
                low, high = limits(name, section_of(at))
                chord_pcs = pcs(tonic, slot)
                if i in arpeggio:
                    lo, hi = band(low, high, 46 if r != 'keys' else 55, 30)
                    root = nearest(chord_pcs[:1], lo+3, lo, hi)
                    q = QUALITIES[DEGREES[slot[0]][1]] if '/' not in slot[0] else QUALITIES['dom7' if slot[0].startswith('V7') else 'dim7']
                    top = root+12+(q[3] if len(q) > 3 else q[2])
                    voicing = [root, root+q[2], root+12+q[1], top]
                    if intensity(at) > .7 and root+24+q[1] <= hi:
                        voicing.append(root+24+q[1])  # register expansion at the climax
                    voicing = [p if p <= hi else p-12 for p in voicing]
                    figure = voicing + voicing[-2:0:-1]
                    offset = int((at-start)/.5)
                    for t in range(int(span/.5)):
                        put(part, at+t*.5, .5, figure[(offset+t) % len(figure)])
                elif r == 'bass':
                    target = low+5-(12 if intensity(at) > .7 else 0)
                    put(part, at, span, nearest(chord_pcs[:1], max(low, target), low, high))
                else:
                    lo, hi = band(low, high, 62, 16)
                    if previous is not None and lo <= previous <= hi and previous % 12 not in chord_pcs:
                        resolution = step(previous, set(chord_pcs), -1, lo, hi)
                        if 0 < previous-resolution <= 2 and span >= 2:
                            put(part, at, 1, previous)  # suspension: held over the change, then down
                            put(part, at+1, span-1, resolution)
                            previous = resolution
                            continue
                    pitch = nearest(chord_pcs[1:] or chord_pcs, previous if previous is not None else lo+4, lo, hi)
                    put(part, at, span, pitch)
                    previous = pitch
    score.editorial.minor = minor
    score.editorial.phrases = phrases
    return finish(score, total)


def melody(rng, part, name, tonic, phrases, start, end, kind, slots, previous, section_of, intensity):
    low, high = limits(name, section_of(start))
    floor = max(low, min(high-12, 62))
    top = min(high, floor+12+round(12*intensity(start+8)))
    if previous is None:
        previous = (floor+top)//2
    previous = max(floor, min(top, previous))
    if kind == 'codetta':
        pitch = nearest(pcs(tonic, slots[0])[:1], previous, floor, top)
        put(part, start, min(4, end-start), pitch)
        return pitch
    bars = [rng.choice(RHYTHMS) for _ in range(3)] + [(4,) if kind == 'full' else (2, 2)]
    at = start
    for b, bar in enumerate(bars):
        for value in bar:
            slot = harmony_at(phrases, at)
            chord_pcs = pcs(tonic, slot)
            key_pcs = scale(tonic, slot[2], slot[1]) | set(chord_pcs)
            if b == 3 and value == bar[-1]:
                pitch = nearest(chord_pcs[:1] if kind == 'full' else chord_pcs, previous, floor, top)
            elif at == start:
                leap = previous+rng.choice([5, 8, 9])
                # Opening leap; near the climax the line leaps to the top of its widened register.
                pitch = nearest(chord_pcs, top-1 if intensity(start+8) > .75 else leap, floor, top)
            elif (at-start) % SLOT == 0:
                pitch = nearest(chord_pcs, previous-rng.choice([1, 2, 3]), floor, top)
                if value >= 2 and rng.random() < .4:
                    above = step(pitch, key_pcs, 1, floor, top)
                    if above > pitch:
                        put(part, at, 1, above)  # appoggiatura resolving down onto the chord tone
                        put(part, at+1, value-1, pitch)
                        previous = pitch
                        at += value
                        continue
            else:
                pitch = step(previous, key_pcs, -1 if rng.random() < .65 else 1, floor, top)
            put(part, at, min(value, end-at), pitch)
            previous = pitch
            at += value
    return previous


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Melody, harmony and swells remain fixed; rubato-free touch inside each marked level is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
