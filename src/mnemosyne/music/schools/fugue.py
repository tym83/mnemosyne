"""Fugue: subject and answer at the fifth, countersubject, sequential episodes, stretto and pedal point."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark
from .renaissance_polyphony import groups
from .tonal import MAJOR, HARMONIC_MINOR, band

CONSONANT = {0, 3, 4, 7, 8, 9}
BAR_ONE = ((1, .5, .5, 1, 1), (1.5, .5, 1, 1), (1, 1, .5, .5, 1), (.5, .5, 1, 1, 1))
BAR_TWO = ((.5, .5, .5, .5, .5, .5, 1), (.25, .25, .25, .25, .5, .5, 1, 1), (1, .5, .5, 2), (.5, .5, 1, .5, .5, 1))


def scale_pitches(tonic, minor, low, high):
    pcs = {(tonic+x) % 12 for x in (HARMONIC_MINOR if minor else MAJOR)}
    return [p for p in range(low, high+1) if p % 12 in pcs]


def make_subject(rng, tonic, minor, low, high):
    """Two bars: a characteristic head, running continuation, close on tonic or third."""
    pool = scale_pitches(tonic, minor, low, high)
    centre = (low+high)/2
    start_pc = (tonic+rng.choice([0, 7])) % 12
    index = min((j for j, p in enumerate(pool) if p % 12 == start_pc), key=lambda j: abs(pool[j]-centre))
    values = list(rng.choice(BAR_ONE)) + list(rng.choice(BAR_TWO))
    leap_at = rng.randrange(1, 4)
    notes, at = [], 0.
    for k, value in enumerate(values):
        if k == len(values)-1:
            ends = [j for j, p in enumerate(pool) if (p-tonic) % 12 in (0, 3, 4)]
            index = min(ends, key=lambda j: abs(j-index))
        elif k == leap_at:
            index += rng.choice([-4, -3, 3, 4])
        elif k > 0:
            index += rng.choice([-1, -1, 1]) if value < 1 else rng.choice([-1, 1, 2, -2])
        index = max(0, min(len(pool)-1, index))
        notes.append((at, value, pool[index]))
        at += value
    return notes


def answer(subject, tonic):
    """At the fifth; a subject that opens on the dominant is answered by the tonic (tonal answer)."""
    out = [(a, v, p+7) for a, v, p in subject]
    if (subject[0][2]-tonic) % 12 == 7:
        out[0] = (out[0][0], out[0][1], subject[0][2]+5)
    return out


def fit(notes, low, high):
    """Shift a whole statement by octaves into [low, high] (keeps every interval)."""
    lo, hi = min(p for _, _, p in notes), max(p for _, _, p in notes)
    best = min(range(-48, 49, 12), key=lambda o: (max(0, low-(lo+o))+max(0, (hi+o)-high), abs(o)))
    return [(a, v, p+best) for a, v, p in notes]


def countersubject(rng, against, low, high):
    """Complementary rhythm to the answer, consonant at each onset, stepwise in between."""
    notes, previous = [], None
    length = against[-1][0]+against[-1][1]
    beat = 0.
    while beat < length:
        onsets = [n for n in against if beat <= n[0] < beat+1]
        values = (1,) if len(onsets) >= 2 else (.5, .5)
        at = beat
        for value in values:
            sounding = next((p for a, v, p in against if a <= at < a+v), None)
            pool = [p for p in range(low, high+1) if sounding is None or (p-sounding) % 12 in (3, 4, 8, 9, 0, 7)]
            if previous is None:
                target = (sounding or (low+high)//2) - 8
            else:
                target = previous+rng.choice([-2, -1, 1, 2])
            pitch = min(pool, key=lambda p: (abs(p-target), p))
            notes.append((at, value, pitch))
            previous = pitch
            at += value
        beat += 1
    return notes


def clash(a, b):
    count = 0
    for x0, xv, xp in a:
        for y0, yv, yp in b:
            if x0 < y0+yv and y0 < x0+xv and abs(xp-yp) % 12 not in CONSONANT | {5}:
                count += 1
    return count


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'fugue', choices=choices)
    tonic = int(plan.get('tonic', 60)) % 12
    minor = rng.random() < .6
    names = ENSEMBLES[plan['ensemble']]
    lines = groups(names)
    n = len(lines)
    sec0 = sections[0][2]
    # Each voice keeps its own tessitura (about a twelfth), spaced from soprano to bass.
    centres = [76 - k*(28/max(1, n-1)) for k in range(n)]
    ranges = [band(*limits(names[g[0]], sec0), centres[k], 19) for k, g in enumerate(lines)]
    top = n//2 if n > 2 else 0
    subject = make_subject(rng, tonic, minor, *ranges[top])
    L = subject[-1][0]+subject[-1][1]
    events = [[] for _ in range(n)]
    entries = []
    final_len = 4
    end_body = total-final_len

    def place(line, at, notes, kind):
        notes = fit(notes, *ranges[line])
        placed = [(at+a, v, p) for a, v, p in notes if at+a < end_body]
        placed = [(a, min(v, end_body-a), p) for a, v, p in placed]
        events[line].extend(placed)
        if placed:
            entries.append({'at': at, 'line': line, 'kind': kind, 'pitches': [p for _, _, p in placed],
                            'end': placed[-1][0]+placed[-1][1]})
        return placed

    # Exposition: subject, answer, subject, answer... each voice then keeps the countersubject.
    order = list(range(n))
    if rng.random() < .5:
        order.reverse()
    ans = answer(subject, tonic)
    cs = None
    at = 0.
    for k, line in enumerate(order):
        statement = subject if k % 2 == 0 else ans
        placed = place(line, at, statement, 'subject' if k % 2 == 0 else 'answer')
        if k > 0:
            prev = order[k-1]
            if cs is None:
                lo, hi = ranges[prev]
                cs = countersubject(rng, [(a-at, v, p) for a, v, p in placed], lo, hi)
                cs_ref = placed[0][2]
            shifted = [(a, v, p-cs_ref+placed[0][2]) for a, v, p in cs]
            place(prev, at, shifted, 'countersubject')
        at += L
    exposition_end = at
    # Plan of the end: stretto, then the subject over a dominant pedal, then the final chord.
    distances = [d for d in (L/2, L*3/4, L/4) if d >= 1]
    stretto_len = L+(n-1)*max(distances)
    pedal_len = L
    stretto_at = max(exposition_end, end_body-pedal_len-stretto_len)
    keys = (3, 7, 5) if minor else (9, 5, 7)
    at, m = exposition_end, 0
    head = [x for x in subject if x[0] < 2] or subject[:2]
    span = head[-1][0]+head[-1][1]
    while at+span*3+L <= stretto_at:
        # Episode: the subject head in a descending sequence, imitated a third lower;
        # the bass moves through a chain of fifths.
        reps = 3
        voice, follower = order[m % n], order[(m+1) % n]
        pool = scale_pitches(tonic, minor, 0, 127)
        for r in range(reps):
            fragment = []
            for a, v, p in head:
                j = min(range(len(pool)), key=lambda j: abs(pool[j]-p))
                fragment.append((a, v, pool[max(0, j-r)]))
            place(voice, at+r*span, fragment, 'episode')
            if n > 2:
                # The follower imitates half a beat later, a third lower, inside the same unit.
                echo = [(a+.5, min(v, span-a-.5), p-(3 if minor else 4)) for a, v, p in fragment if a+.5 < span]
                place(follower, at+r*span, echo, 'episode')
        bass = n-1
        if bass not in (voice, follower):
            root = (tonic+keys[m % len(keys)]) % 12
            lo, hi = ranges[bass]
            for r in range(reps):
                pitch = min((p for p in range(lo, hi+1) if p % 12 == (root+7*(reps-1-r)) % 12),
                            key=lambda p: abs(p-(lo+7)))
                place(bass, at+r*span, [(0, span, pitch)], 'episode-bass')
        at += span*reps
        # Middle entry in a related key.
        key = keys[m % len(keys)]
        line = order[(m+2) % n]
        placed = place(line, at, [(a, v, p+key) for a, v, p in subject], 'middle')
        companion = order[(m+3) % n]
        if companion != line and cs is not None:
            place(companion, at, [(a, v, p-cs_ref+placed[0][2]) for a, v, p in cs], 'countersubject')
        at += L
        m += 1
    # Stretto: overlapping entries at the closest distance that clashes least.
    stretto_at = max(stretto_at, at)
    best = None
    for d in distances:
        trial = []
        for k in range(n):
            notes = fit(subject if k % 2 == 0 else ans, *ranges[order[k]])
            trial.append([(stretto_at+k*d+a, v, p) for a, v, p in notes])
        score_ = sum(clash(trial[x], trial[y]) for x in range(n) for y in range(x+1, n))
        if best is None or score_ < best[0]:
            best = (score_, d)
    distance = best[1]
    for k in range(n):
        place(order[k], stretto_at+k*distance, subject if k % 2 == 0 else ans, 'stretto')
    pedal_at = stretto_at+L+(n-1)*distance
    # Dominant pedal in the lowest voice; the top voice states the subject over it.
    low_line = n-1
    lo, hi = ranges[low_line]
    dominant = min((p for p in range(lo, hi+1) if p % 12 == (tonic+7) % 12), key=lambda p: abs(p-(lo+5)))
    if pedal_at < end_body:
        events[low_line] = [e for e in events[low_line] if e[0] < pedal_at]
        events[low_line] = [(a, min(v, pedal_at-a), p) for a, v, p in events[low_line]]
        place(low_line, pedal_at, [(0, end_body-pedal_at, dominant)], 'pedal')
        if n > 1:
            events[0] = [(a, min(v, pedal_at-a), p) for a, v, p in events[0] if a < pedal_at]
            place(0, pedal_at, subject, 'pedal-subject')
    # Free counterpoint fills every remaining gap after a voice's first entry.
    first = {line: min(a for a, _, _ in events[line]) for line in range(n) if events[line]}
    scale_pcs = {(tonic+x) % 12 for x in (HARMONIC_MINOR if minor else MAJOR)}
    fast = sum(s['density'] for _, _, s in sections)/len(sections) >= .6
    for line in range(n):
        lo, hi = ranges[line]
        mine = sorted(events[line])
        gaps, cursor = [], first.get(line, 0)
        for a, v, p in mine:
            if a > cursor+1e-9:
                gaps.append((cursor, a))
            cursor = max(cursor, a+v)
        if cursor < end_body:
            gaps.append((cursor, end_body))
        for a, b in gaps:
            previous = next((p for x, v, p in reversed(mine) if x < a), (lo+hi)//2)
            t = a
            while t < b-1e-9:
                value = min(rng.choice([.5, .5, 1] if fast else [1, 1, .5]), b-t)
                others = [p for other in range(n) if other != line for x, v, p in events[other] if x < t+value and t < x+v]
                candidates = [previous+s for s in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5)]
                if rng.random() < .5:
                    candidates[0], candidates[1] = candidates[1], candidates[0]
                pitch = None
                for c in candidates:
                    if lo <= c <= hi and c % 12 in scale_pcs and all(abs(c-o) % 12 in CONSONANT | {5} for o in others):
                        pitch = c
                        break
                if pitch is not None:
                    events[line].append((t, value, pitch))
                    previous = pitch
                t += value
    # Final chord on the tonic; a minor fugue ends with a major third (tierce de Picardie).
    chord_pcs = [tonic, (tonic+4) % 12, (tonic+7) % 12]
    for line in range(n):
        lo, hi = ranges[line]
        pc = tonic if line in (0, n-1) else chord_pcs[1 + line % 2]
        pitch = min((p for p in range(lo, hi+1) if p % 12 == pc), key=lambda p: abs(p-(lo+hi)/2))
        events[line].append((end_body, final_len, pitch))
    for line, group in enumerate(lines):
        for i in group:
            for a, b, sec in sections:
                mark(score.parts[i], a, 'Fugue' if a == 0 else sec['character'])
            for at, value, pitch in sorted(events[line]):
                if value <= 0:
                    continue
                plow, phigh = limits(names[i], next(s for x, y, s in sections if x <= at < y))
                while pitch > phigh:
                    pitch -= 12
                while pitch < plow:
                    pitch += 12
                put(score.parts[i], at, value, pitch)
    score.editorial.subject = subject
    score.editorial.answer = ans
    score.editorial.entries = entries
    score.editorial.minor = minor
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Subject, answer, episodes and stretto remain fixed; the weight of each entry is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
