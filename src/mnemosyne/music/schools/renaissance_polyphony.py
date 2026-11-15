"""Imitative polyphony: points of imitation, smooth consonant lines, suspension cadences on the final."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, RANGES, setup, limits, put, finish
from .chant import MODES, degree_pitch, place_final
from .material import mark

CONSONANT = {0, 3, 4, 7, 8, 9}
CADENCE = 6  # quarters: approach, suspension and resolution, final
# Cadential formulas in degrees from the final: (degree, quarters) per role.
FORMULAS = {'cantizans': ((7, 3), (6, 1), (7, 2)),
            'tenorizans': ((2, 2), (1, 2), (0, 2)),
            'bassizans': ((-5, 2), (-3, 2), (-7, 2)),
            'altizans': ((4, 2), (4, 2), (4, 2))}
# Phrygian: the semitone lies above the final, so bass and alto avoid the tritone with F.
PHRYGIAN = {'bassizans': ((-5, 2), (-4, 2), (-7, 2)), 'altizans': ((4, 2), (3, 2), (4, 2))}


def subject(rng):
    """A short stepwise head: long opening, a leap at most once, shorter values, long close."""
    degrees, d = [0], 0
    size = rng.randrange(5, 9)
    leap = rng.randrange(1, 3)
    for k in range(1, size):
        if k == leap:
            d += rng.choice([2, 3, 4, -2])
        else:
            d += rng.choice([-1, 1]) if d <= 4 else -1
        degrees.append(d)
    values = [2] + [rng.choice([1, 1, 2, .5]) for _ in range(size-2)] + [2]
    # Paired eighths only: a lone half-beat would leave the line off the beat.
    fixed, k = [], 0
    while k < len(values):
        if values[k] == .5:
            fixed += [.5, .5] if k+1 < len(values)-1 else [1]
            k += 2 if k+1 < len(values)-1 else 1
        else:
            fixed.append(values[k])
            k += 1
    degrees = degrees[:len(fixed)]
    while len(degrees) < len(fixed):
        degrees.append(degrees[-1]-1)
    return list(zip(degrees, fixed))


def groups(names):
    """Up to four imitating lines, highest first; extra parts double a line in their own octave."""
    order = sorted(range(len(names)), key=lambda i: (-(RANGES[names[i]][0]+RANGES[names[i]][1]), i))
    lines = min(4, len(names))
    return [[i for k, i in enumerate(order) if k*lines//len(names) == line] for line in range(lines)]


def sounding(events, at, until):
    return [d for a, l, d in events if d is not None and a < until and at < a+l]


def head(theme, gap):
    """The imitated head: at least three notes, and no longer than the distance to the next entry."""
    out, length = [], 0
    for degree, value in theme:
        if len(out) >= 3 and length+value > gap:
            break
        out.append((degree, value))
        length += value
    return out


def exposition(theme, order, gap, answer, finals, a, room):
    """Entries of the head every `gap` quarters, alternating the final and the answer interval."""
    events = [[] for _ in finals]
    entries = []
    top, bottom = max(d for d, _ in theme), min(d for d, _ in theme)
    for k, line in enumerate(order):
        at = a+k*gap
        fin, lo, hi = finals[line]
        offset = 0 if k % 2 == 0 else answer
        if top+offset > hi and bottom+offset-7 >= lo-2:
            offset -= 7
        elif bottom+offset < lo and top+offset+7 <= hi+2:
            offset += 7
        entries.append((at, line, offset))
        for degree, value in head(theme, gap):
            if at >= a+room:
                break
            events[line].append((at, min(value, a+room-at), degree+offset))
            at += value
    return events, entries


def clashes(events, finals, n):
    count = 0
    for x in range(n):
        for y in range(x+1, n):
            for a, la, da in events[x]:
                for b, lb, db in events[y]:
                    if a < b+lb and b < a+la and min(la, lb) >= 1:
                        interval = abs(degree_pitch(finals[x][0], da)-degree_pitch(finals[y][0], db)) % 12
                        if interval not in CONSONANT and not (interval == 5 and n-1 not in (x, y)):
                            count += 1
    return count


PERFECT = {0, 7}  # unison/octave and fifth, as pitch-class intervals


def at_time(events, t):
    """Degree sounding from `t` on (None for a rest or silence)."""
    found = None
    for a, l, d in events:
        if a <= t < a+l:
            found = d
    return found


def before(events, t):
    """Degree sounding just before `t` (None for a rest or silence)."""
    found = None
    for a, l, d in events:
        if a < t <= a+l:
            found = d
    return found


def parallel(x0, x1, y0, y1):
    """Both voices move the same way into the same perfect interval they left."""
    if None in (x0, x1, y0, y1):
        return False
    mx, my = x1-x0, y1-y0
    if mx == 0 or my == 0 or (mx > 0) != (my > 0):
        return False
    first, second = abs(x0-y0) % 12, abs(x1-y1) % 12
    return first == second and first in PERFECT


def pitches(line, degrees, finals):
    return [None if d is None else degree_pitch(finals[line][0], d) for d in degrees]


def parallels(events, finals, n):
    """Consecutive verticals in similar motion forming the same perfect interval, over all voice pairs."""
    found = []
    for x in range(n):
        for y in range(x+1, n):
            onsets = sorted({a for a, _, _ in events[x]} | {a for a, _, _ in events[y]})
            verticals = [(t, *pitches(x, [at_time(events[x], t)], finals), *pitches(y, [at_time(events[y], t)], finals))
                         for t in onsets]
            for (t0, x0, y0), (t1, x1, y1) in zip(verticals, verticals[1:]):
                if parallel(x0, x1, y0, y1):
                    found.append((t1, x, y))
    return found


def makes_parallel(line, d, at, value, events, finals, n, cadence_at, cadence):
    """Would `d` on [at, at+value) move in parallel fifths or octaves with any other line?"""
    p = degree_pitch(finals[line][0], d)
    x0 = before(events[line], at)
    x0 = None if x0 is None else degree_pitch(finals[line][0], x0)
    moves = [(at, x0, p)]
    if at+value == cadence_at:
        moves.append((cadence_at, p, degree_pitch(finals[line][0], cadence[line])))
    for other in range(n):
        if other == line:
            continue
        for t, a, b in moves:
            if t == cadence_at and at+value == cadence_at:
                y1 = cadence[other]
            else:
                y1 = at_time(events[other], t)
            y0 = before(events[other], t)
            y0, y1 = pitches(other, [y0, y1], finals)
            if parallel(a, b, y0, y1):
                return True
    return False


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'renaissance_polyphony', choices=choices)
    mode = MODES[rng.randrange(8)]
    names = ENSEMBLES[plan['ensemble']]
    lines = groups(names)
    n = len(lines)
    roles = ['cantizans'] + ['altizans']*(n-3) + (['tenorizans', 'bassizans'] if n >= 3 else ['tenorizans'] if n == 2 else [])
    raise_leading = mode['final'] != 4  # Phrygian cadences keep the whole step below
    points = []
    line_events, line_finals = [], []  # per point: the lines in degrees and their finals
    for start, end, sec in sections:
        finals = []
        for group in lines:
            rep = names[group[0]]
            finals.append(place_final(mode['final'], -3, 8, *limits(rep, sec)))
        length = end-start
        count = max(1, int(length // (24 if sec['density'] < .6 else 18)))
        bounds = [start + (length*k/count) for k in range(count+1)]
        bounds = [start + round((b-start)*2)/2 for b in bounds[:-1]] + [end]
        for a, b in zip(bounds, bounds[1:]):
            if b-a < CADENCE+2:
                # Too short for a point: every line sustains its place in the final sonority.
                for line, group in enumerate(lines):
                    degree = FORMULAS[roles[line]][-1][0]
                    for i in group:
                        plow, phigh = limits(names[i], sec)
                        pitch = degree_pitch(place_final(mode['final'], -3, 8, plow, phigh)[0], degree)
                        while pitch > phigh:
                            pitch -= 12
                        while pitch < plow:
                            pitch += 12
                        put(score.parts[i], a, b-a, pitch)
                continue
            theme = subject(rng)
            span = sum(v for _, v in theme)
            room = b-a-CADENCE
            base = 4 if sec['density'] < .6 else 2
            gaps = [g for g in (base, base*1.5, base/2, base*2) if g >= 1 and g*(n-1)+span <= room] or [1]
            order = list(range(n)) if rng.random() < .5 else list(range(n))[::-1]
            candidates = [(g, answer) for g in gaps for answer in (4, -3, 0)]
            rng.shuffle(candidates)
            # The composer tries entry distances and answer intervals: no parallel fifths or
            # octaves between the entries first, then the fewest clashes.
            def cost(c):
                trial = exposition(theme, order, c[0], c[1], finals, a, room)[0]
                return len(parallels(trial, finals, n)), clashes(trial, finals, n)
            gap, answer = min(candidates, key=cost)
            events, entries = exposition(theme, order, gap, answer, finals, a, room)
            points.append({'entries': entries, 'subject': head(theme, gap), 'gap': gap})
            cadence_at = b-CADENCE
            cadence = [FORMULAS[roles[line]][0][0] for line in range(n)]
            # Free counterpoint after each entry: steps first, consonant with every known line.
            for line in order:
                fin, lo, hi = finals[line]
                at = max(a+l for a, l, _ in events[line]) if events[line] else a
                previous = events[line][-1][2] if events[line] else 0
                while at < cadence_at:
                    value = min(rng.choice([1, 2, 1, .5]), cadence_at-at)
                    if value == .5 and at+1 <= cadence_at:
                        value = 1 if rng.random() < .5 else .5
                    others = [(other, sounding(events[other], at, at+value)) for other in range(n) if other != line]
                    steps = [1, -1, 2, -2, 3, -3, 4, -4]
                    if rng.random() < .5:
                        steps[0], steps[1] = steps[1], steps[0]
                    choice = None
                    for s in steps:
                        d = previous+s
                        if not lo <= d <= hi:
                            continue
                        if makes_parallel(line, d, at, value, events, finals, n, cadence_at, cadence):
                            continue
                        pitch = degree_pitch(fin, d)
                        ok = True
                        for other, degrees in others:
                            for od in degrees:
                                interval = abs(pitch-degree_pitch(finals[other][0], od)) % 12
                                lowest = other == n-1 or line == n-1
                                if interval not in CONSONANT and not (interval == 5 and not lowest):
                                    ok = ok and value == .5 and abs(s) == 1  # passing tone only
                        if ok:
                            choice = d
                            break
                    events[line].append((at, value, choice))
                    if choice is not None:
                        previous = choice
                    at += value
            for line in range(n):
                at = cadence_at
                formula = FORMULAS[roles[line]]
                if mode['final'] == 4 and roles[line] in PHRYGIAN:
                    formula = PHRYGIAN[roles[line]]
                for degree, value in formula:
                    events[line].append((at, value, degree))
                    at += value
            line_events.append(events)
            line_finals.append(finals)
            for line, group in enumerate(lines):
                role = roles[line]
                for i in group:
                    plow, phigh = limits(names[i], sec)
                    fin = place_final(mode['final'], -3, 8, plow, phigh)[0]
                    if a == start:
                        mark(score.parts[i], a, f"Mode {mode['number']}; point of imitation every {gap} quarters")
                    for at, value, degree in events[line]:
                        if degree is None:
                            continue
                        pitch = degree_pitch(fin, degree)
                        if role == 'cantizans' and degree == 6 and at >= cadence_at and raise_leading:
                            pitch = degree_pitch(fin, 7)-1  # musica ficta: raised leading tone
                        while pitch > phigh:
                            pitch -= 12
                        while pitch < plow:
                            pitch += 12
                        put(score.parts[i], at, value, pitch)
    score.editorial.mode = mode
    score.editorial.points = points
    score.editorial.lines = lines
    score.editorial.line_events = line_events
    score.editorial.line_finals = line_finals
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Points of imitation, mode and cadences remain fixed; the swell of each line is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
