"""Symphony grammar v2: the plan is the score's skeleton, and nothing sounds that the plan does not name.

v1 wrote one fixed texture (4/4, the same root cycle, constant harp figuration) whatever the plan said.
v2 realizes what the composer writes: meter per section, mode and harmonic progression, and layers.
A layer names its instruments, role, material, accompaniment pattern, dynamic and register. An
instrument that no layer of a section names is silent there. Unknown plan fields are rejected, so the
composer always knows what is realized. Tempo is per movement; meter may change per section.
"""
from fractions import Fraction
import hashlib
import math
import random

from .instrumentarium import REGISTRY, audio_ensemble
from .orchestration import Event, Line, orchestrate

MODES = {
    'major': [0, 2, 4, 5, 7, 9, 11], 'minor': [0, 2, 3, 5, 7, 8, 10], 'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'dorian': [0, 2, 3, 5, 7, 9, 10], 'phrygian': [0, 1, 3, 5, 7, 8, 10], 'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10], 'locrian': [0, 1, 3, 5, 6, 8, 10],
    'pentatonic': [0, 2, 4, 7, 9], 'minor_pentatonic': [0, 3, 5, 7, 10], 'whole_tone': [0, 2, 4, 6, 8, 10],
    'octatonic': [0, 1, 3, 4, 6, 7, 9, 10], 'hijaz': [0, 1, 4, 5, 7, 8, 10], 'chromatic': list(range(12)),
}
DYNAMICS = {'ppp': 24, 'pp': 36, 'p': 48, 'mp': 60, 'mf': 72, 'f': 88, 'ff': 104, 'fff': 118}
ROLES = {'melody': 'melody', 'counter': 'counter_line', 'bass': 'bass', 'pad': 'harmony_pad',
         'chorale': 'harmony_pad', 'drone': 'harmony_pad', 'ostinato': 'figuration',
         'figuration': 'figuration', 'points': 'counter_line', 'percussion': 'percussion_layer'}
PATTERNS = {'line', 'sustain', 'waltz', 'march', 'pulse', 'offbeat', 'arpeggio', 'repeated', 'hits',
            'rolls', 'walking', 'ostinato', 'points', 'tremolo'}
TECHNIQUES = {'arco', 'pizzicato', 'staccato', 'col_legno', 'harmonics', 'tremolo', 'sustain'}
TRANSFORMS = {'identity', 'inversion', 'augmentation', 'diminution', 'retrograde', 'fragmentation',
              'reharmonisation'}

PLAN_KEYS = {'version', 'title', 'seed', 'concept', 'method', 'orchestra', 'themes', 'rows', 'movements',
             'school_settings', 'notagen_material', 'held_swell', 'notes'}
MOVEMENT_KEYS = {'title', 'character', 'form', 'tempo', 'centre', 'mode', 'schools', 'sections', 'notes'}
SECTION_KEYS = {'role', 'bars', 'meter', 'theme', 'transform', 'shift', 'mode', 'progression',
                'harmonic_rhythm', 'layers', 'schools', 'notes'}
LAYER_KEYS = {'instruments', 'role', 'material', 'transform', 'pattern', 'dynamic', 'register', 'density',
              'technique', 'bars', 'octave_double', 'time_scale', 'notes'}
GRID = .125  # onsets of a time-scaled line fall on a 1/32-note grid; the mean ratio is kept exactly


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def meter(text):
    try:
        num, den = (int(x) for x in str(text).split('/'))
    except ValueError:
        raise ValueError(f'meter must look like 3/4, got {text!r}')
    if not 1 <= num <= 15 or den not in (2, 4, 8, 16):
        raise ValueError(f'unsupported meter {text}')
    bar = Fraction(num * 4, den)
    compound = den == 8 and num % 3 == 0 and num > 3
    beat = Fraction(3, 2) if compound else Fraction(4, den)
    return bar, beat


def strict(obj, allowed, where):
    if not isinstance(obj, dict):
        raise ValueError(f'{where} must be an object')
    extra = set(obj) - allowed
    if extra:
        raise ValueError(f'{where}: fields {sorted(extra)} are not realized by grammar v2; '
                         f'allowed: {sorted(allowed)}. Write intent the grammar cannot express in "notes".')


def instruments_of(plan):
    players = audio_ensemble(plan['orchestra'])
    slots = {}
    for p in players:
        slots[p.instrument] = slots.get(p.instrument, 0) + p.divisi
    return slots


def validate(plan, *, study=False):
    from .symphony import FORMS
    from .schools import SCHOOLS
    strict(plan, PLAN_KEYS, 'plan')
    if not plan.get('concept') or not plan.get('method') or not plan.get('title') or type(plan.get('seed')) is not int:
        raise ValueError('title, integer seed, concept and method required')
    if not plan.get('orchestra'):
        raise ValueError('orchestra required: you choose the instruments')
    slots = instruments_of(plan)
    themes = plan.get('themes', {})
    rows = plan.get('rows', {})
    if not themes:
        raise ValueError('cyclic themes required')
    for name, theme in themes.items():
        ps, ds = theme.get('pitches', []), theme.get('durations', [])
        if not ps:
            raise ValueError(f'theme {name}: at least one pitch (a single held tone is a theme too)')
        if len(ps) != len(ds):
            raise ValueError(f'theme {name}: {len(ps)} pitches but {len(ds)} durations; one duration per pitch')
        bad = [p for p in ps if not finite(p) or not 0 <= p <= 127]
        if bad:
            raise ValueError(f'theme {name}: pitches are MIDI numbers 0–127, got {bad}')
        bad = [d for d in ds if not finite(d) or d <= 0 or d * 4 != int(d * 4)]
        if bad:
            raise ValueError(f'theme {name}: durations are quarters in multiples of 0.25 (a sixteenth), got {bad}; '
                             'for an irrational tempo ratio write the theme plainly and give the layer time_scale')
        if not theme.get('source'):
            raise ValueError(f'theme {name}: provenance (source) required')
    for name, row in rows.items():
        if sorted(int(x) % 12 for x in row) != list(range(12)) or len(row) != 12:
            raise ValueError(f'row {name}: twelve distinct pitch classes')
    mvs = plan.get('movements', [])
    if not 3 <= len(mvs) <= 5 and not (study and 1 <= len(mvs) <= 5):
        raise ValueError('a symphony has 3–5 movements')
    heard, sounding = [], set()
    seconds = 0.
    for mi, mv in enumerate(mvs):
        where = f'movement {mi+1}'
        strict(mv, MOVEMENT_KEYS, where)
        if not finite(mv.get('tempo')) or not 30 <= mv['tempo'] <= 240:
            raise ValueError(f'{where}: tempo 30–240 (quarter notes per minute)')
        if not mv.get('character'):
            raise ValueError(f'{where}: character required')
        if not finite(mv.get('centre')) or not 0 <= mv['centre'] <= 127:
            raise ValueError(f'{where}: centre (MIDI) required')
        if mv.get('mode', 'major') not in MODES:
            raise ValueError(f'{where}: mode must be one of {sorted(MODES)}')
        secs = mv.get('sections', [])
        form = mv.get('form')
        if form == 'free':
            if not secs or any(not isinstance(s.get('role'), str) or not s['role'] for s in secs):
                raise ValueError(f'{where}: a free form names every section role')
        elif form not in FORMS or [s.get('role') for s in secs] != FORMS[form]:
            raise ValueError(f'{where}: form must be "free" or one of {sorted(FORMS)} with its section order')
        used = set()
        quarters = Fraction(0)
        for si, sec in enumerate(secs):
            sw = f'{where} section {si+1} ({sec.get("role")})'
            strict(sec, SECTION_KEYS, sw)
            if type(sec.get('bars')) is not int or sec['bars'] < 1:
                raise ValueError(f'{sw}: whole bars required')
            bar, _ = meter(sec.get('meter', '4/4'))
            quarters += bar * sec['bars']
            if sec.get('theme') is not None:
                if sec['theme'] not in themes:
                    raise ValueError(f'{sw}: unknown theme')
                used.add(sec['theme'])
            if sec.get('transform', 'identity') not in TRANSFORMS:
                raise ValueError(f'{sw}: transform one of {sorted(TRANSFORMS)}')
            if not finite(sec.get('shift', 0)):
                raise ValueError(f'{sw}: shift in semitones')
            if sec.get('mode', mv.get('mode', 'major')) not in MODES:
                raise ValueError(f'{sw}: unknown mode')
            prog = sec.get('progression', [1])
            scale = MODES[sec.get('mode', mv.get('mode', 'major'))]
            if not isinstance(prog, list) or not prog or any(type(d) is not int or not 1 <= abs(d) <= len(scale) for d in prog):
                raise ValueError(f'{sw}: progression is a list of scale degrees 1..{len(scale)} (negative = an octave lower)')
            if type(sec.get('harmonic_rhythm', 1)) is not int or sec.get('harmonic_rhythm', 1) < 1:
                raise ValueError(f'{sw}: harmonic_rhythm = bars per chord')
            layers = sec.get('layers', [])
            if not isinstance(layers, list):
                raise ValueError(f'{sw}: layers list required ([] means general pause)')
            for li, layer in enumerate(layers):
                lw = f'{sw} layer {li+1}'
                strict(layer, LAYER_KEYS, lw)
                names = layer.get('instruments')
                if not names or any(n not in slots for n in names):
                    raise ValueError(f'{lw}: instruments must come from your orchestra {sorted(slots)}')
                if layer.get('role') not in ROLES:
                    raise ValueError(f'{lw}: role one of {sorted(ROLES)}')
                unpitched = [n for n in names if REGISTRY[n].get('unpitched')]
                if unpitched and (layer['role'] != 'percussion' or len(unpitched) != len(names)):
                    raise ValueError(f'{lw}: unpitched {unpitched} play only in a percussion layer, alone')
                if layer['role'] == 'percussion' and len(unpitched) != len(names):
                    raise ValueError(f'{lw}: a percussion layer holds unpitched instruments only')
                material = layer.get('material', 'harmony')
                kind, _, ref = str(material).partition(':')
                if kind == 'theme' and ref not in themes or kind == 'row' and ref not in rows:
                    raise ValueError(f'{lw}: unknown material {material}')
                if kind == 'school' and ref not in SCHOOLS:
                    raise ValueError(f'{lw}: unknown school {ref}')
                if kind == 'notagen' and not plan.get('notagen_material', {}).get('source'):
                    raise ValueError(f'{lw}: NotaGen material requires selected, archived notagen_material')
                if kind not in ('theme', 'row', 'school', 'harmony', 'scale', 'notagen'):
                    raise ValueError(f'{lw}: material is theme:<name>, row:<name>, school:<name>, notagen, harmony or scale')
                if kind == 'theme':
                    used.add(ref)
                if layer.get('pattern', 'line') not in PATTERNS:
                    raise ValueError(f'{lw}: pattern one of {sorted(PATTERNS)}')
                if layer.get('technique', 'arco') not in TECHNIQUES:
                    raise ValueError(f'{lw}: technique one of {sorted(TECHNIQUES)}')
                if layer.get('transform', 'identity') not in TRANSFORMS:
                    raise ValueError(f'{lw}: unknown transform')
                dyn = layer.get('dynamic', 'mf')
                dyn = dyn if isinstance(dyn, list) else [dyn]
                if not 1 <= len(dyn) <= 2 or any(d not in DYNAMICS for d in dyn):
                    raise ValueError(f'{lw}: dynamic is one of {list(DYNAMICS)} or [from, to]')
                reg = layer.get('register')
                if reg is not None and (len(reg) != 2 or not all(finite(x) for x in reg) or not 0 <= reg[0] <= reg[1] <= 127):
                    raise ValueError(f'{lw}: register is [low, high] in MIDI 0–127 with low ≤ high (equal pins one pitch), got {reg}')
                if not finite(layer.get('density', .5)) or not 0 < layer.get('density', .5) <= 1:
                    raise ValueError(f'{lw}: density in (0, 1]')
                scale_t = layer.get('time_scale', 1)
                if not finite(scale_t) or not .25 <= scale_t <= 4:
                    raise ValueError(f'{lw}: time_scale in [0.25, 4] (duration multiplier: 1.414 = this voice at 1/√2 tempo)')
                span = layer.get('bars')
                if span is not None and (len(span) != 2 or not all(type(x) is int for x in span)
                                         or not 1 <= span[0] <= span[1] <= sec['bars']):
                    raise ValueError(f'{lw}: bars [first, last] inside the section (1-based)')
                sounding.update(names)
        heard.append(used)
        seconds += float(quarters) * 60 / mv['tempo']
    if len(heard) > 1 and not set.intersection(*heard):
        raise ValueError('one cyclic theme must return in every movement')
    if not sounding:
        raise ValueError('nothing sounds: every section has empty layers')
    if not study and not 1200 <= seconds <= 2700:
        raise ValueError(f'symphony must last 20–45 minutes; this plan lasts {seconds/60:.1f}')
    return seconds


def on_grid(q, grid=.125):
    return max(grid, math.floor(q / grid + 1e-9) * grid)


def transform(ps, ds, operation):
    ps, ds = list(ps), list(ds)
    if operation == 'inversion':
        ps = [2 * ps[0] - p for p in ps]
    elif operation == 'retrograde':
        ps.reverse(); ds.reverse()
    elif operation == 'augmentation':
        ds = [d * 2 for d in ds]
    elif operation == 'diminution':
        ds = [max(.25, d / 2) for d in ds]
    elif operation == 'fragmentation':
        ps = ps[:max(1, min(len(ps), max(2, len(ps) // 2)))]; ds = ds[:len(ps)]
    return ps, ds


def place(pitch, instrument, register=None):
    """The octave of pitch class `pitch` nearest to the register's centre, playable and sampled."""
    spec = REGISTRY[instrument]
    if spec.get('unpitched'):
        return spec['comfortable'][0]
    lo, hi = register or spec['comfortable']
    target = (lo + hi) / 2 if register else pitch
    technique = 'arco' if spec['family'] == 'strings' else 'sustain'
    zones = spec['samples'].get('key_ranges', {}).get(technique, [spec['range']])
    options = [pitch + 12 * k for k in range(-10, 11)
               if spec['range'][0] <= pitch + 12 * k <= spec['range'][1]
               and any(a <= round(pitch + 12 * k) <= b for a, b in zones)]
    if not options:
        raise ValueError(f'{instrument} cannot play pitch class of {pitch}')
    inside = [p for p in options if lo <= p <= hi] or options
    return min(inside, key=lambda p: abs(p - target))


def chord(centre, scale, degree, size=3):
    """A chord stacked in thirds of the mode: degree 1 is the centre; negative degrees sound an octave lower."""
    base = abs(degree) - 1
    out = []
    for k in range(size):
        step = base + 2 * k
        out.append(centre + scale[step % len(scale)] + 12 * (step // len(scale)) - (12 if degree < 0 else 0))
    return out


def velocity(dyn, t):
    dyn = dyn if isinstance(dyn, list) else [dyn, dyn]
    a, b = DYNAMICS[dyn[0]], DYNAMICS[dyn[-1]]
    return max(1, min(127, round(a + (b - a) * t)))


def material_stream(kind, ref, plan, mv, sec, layer, mi, harmony_at):
    """An endless (pitch, duration) stream for a layer: theme, row, school reservoir, harmony or scale."""
    from .symphony import school_material
    shift = sec.get('shift', 0)
    if kind == 'theme':
        theme = plan['themes'][ref]
        ps = [p - theme['pitches'][0] + mv['centre'] + shift for p in theme['pitches']]
        ps, ds = transform(ps, theme['durations'], layer.get('transform', sec.get('transform', 'identity')))
        return ps, ds
    if kind == 'notagen':
        m = plan['notagen_material']
        return [p - m['pitches'][0] + mv['centre'] + shift for p in m['pitches']], list(m['durations'])
    if kind == 'row':
        row = plan['rows'][ref]
        return [mv['centre'] + shift + (int(x) - int(row[0])) % 12 for x in row], [1] * 12
    if kind == 'school':
        events = school_material(ref, mv['centre'] + shift, plan['seed'] + mi,
                                 plan.get('school_settings', {}).get(ref))['events']
        melody, last = [], -1
        for at, d, p in events:
            if at > last:
                melody.append((p, max(.25, round(d * 4) / 4))); last = at
        return [p for p, _ in melody], [d for _, d in melody]
    scale = MODES[sec.get('mode', mv.get('mode', 'major'))]
    if kind == 'scale':
        return [mv['centre'] + shift + s for s in scale], [.5] * len(scale)
    return None, None  # harmony: read chord by chord


def realize_section(plan, mi, si, start, slots, rng):
    """Events per (instrument, layer) for one section, at absolute quarter offsets."""
    mv = plan['movements'][mi]
    sec = mv['sections'][si]
    bar_q, beat_q = (float(x) for x in meter(sec.get('meter', '4/4')))
    scale = MODES[sec.get('mode', mv.get('mode', 'major'))]
    centre = mv['centre'] + sec.get('shift', 0)
    prog, hr = sec.get('progression', [1]), sec.get('harmonic_rhythm', 1)
    if sec.get('transform') == 'reharmonisation' and len(prog) > 1:
        prog = prog[1:] + prog[:1]

    def harmony_at(bar):
        return chord(centre, scale, prog[(bar // hr) % len(prog)])

    out = []
    for li, layer in enumerate(sec.get('layers', [])):
        names = layer['instruments']
        role, pattern = layer['role'], layer.get('pattern', 'line')
        density = layer.get('density', .5)
        first, last = layer.get('bars', [1, sec['bars']])
        reg = layer.get('register')
        tech = layer.get('technique')
        kind, _, ref = str(layer.get('material', 'harmony')).partition(':')
        stream_ps, stream_ds = material_stream(kind, ref, plan, mv, sec, layer, mi, harmony_at)
        events = []  # (at, dur, [pitch classes or pitches], t)
        span_bars = last - first + 1
        cursor = 0

        def nxt():
            nonlocal cursor
            p, d = stream_ps[cursor % len(stream_ps)], stream_ds[cursor % len(stream_ds)]
            cursor += 1
            return p, d

        for b in range(first - 1, last):
            a = start + b * bar_q
            t = (b - first + 1) / max(1, span_bars - 1)
            ch = harmony_at(b)
            beats = [a + k * beat_q for k in range(max(1, round(bar_q / beat_q)))]
            if pattern == 'line' and stream_ps:
                # Laid out continuously across the bars; development is the section's transform.
                pass
            elif pattern == 'sustain' or pattern == 'tremolo':
                events.append((a, bar_q, ch if role in ('pad', 'chorale', 'drone') else [ch[0]], t))
            elif pattern == 'waltz':
                if role == 'bass':
                    events.append((beats[0], beat_q, [ch[0]], t))
                else:
                    for x in beats[1:]:
                        events.append((x, on_grid(beat_q * .75), ch, t))
            elif pattern == 'march':
                for k, x in enumerate(beats):
                    if role == 'bass':
                        if k % 2 == 0:
                            events.append((x, on_grid(beat_q * .75), [ch[0] if k % 4 == 0 else ch[2]], t))
                    elif k % 2 == 1 or len(beats) == 1:
                        events.append((x, beat_q * .5, ch, t))
            elif pattern == 'pulse':
                step = beat_q / 2 if density > .6 else beat_q
                x = a
                while x < a + bar_q - 1e-9:
                    events.append((x, on_grid(step * .75), [ch[0]] if role == 'bass' else ch, t)); x += step
            elif pattern == 'offbeat':
                for x in beats:
                    events.append((x + beat_q / 2, beat_q / 2, ch, t))
            elif pattern == 'arpeggio':
                step = .25 if density > .75 else .5
                x, k = a, 0
                tones = ch + [ch[0] + 12]
                while x < a + bar_q - 1e-9:
                    events.append((x, step, [tones[k % len(tones)]], t)); x += step; k += 1
            elif pattern == 'walking':
                for k, x in enumerate(beats):
                    events.append((x, on_grid(beat_q * .75), [ch[k % 3] if k % 2 == 0 else centre + scale[(k + 1) % len(scale)]], t))
            elif pattern == 'hits':
                for k, x in enumerate(beats):
                    if k == 0 or rng.random() < density * .5:
                        events.append((x, min(.5, beat_q / 2), ch, t))
            elif pattern == 'rolls':
                x = a
                while x < a + bar_q - 1e-9:
                    if rng.random() < density:
                        events.append((x, .25, [0], t))
                    x += .25
            elif pattern in ('repeated', 'ostinato'):
                cell = (stream_ps or ch)[:max(2, round(2 + 4 * density))]
                step = beat_q / 2
                x, k = a, 0
                while x < a + bar_q - 1e-9:
                    events.append((x, on_grid(step * .75), [cell[k % len(cell)]], t)); x += step; k += 1
            elif pattern == 'points':
                for k in range(round(bar_q * 2)):
                    if rng.random() < density * .35:
                        source = stream_ps or ch
                        events.append((a + k * .5, .5, [source[rng.randrange(len(source))]], t))
        if pattern == 'line':
            ps, ds = stream_ps, stream_ds
            k = layer.get('time_scale', 1)
            if ps is not None and k != 1:
                # A voice in its own tempo: exact scaled onsets rounded to the grid, so the ratio holds over a phrase.
                onsets, x = [], 0.
                for d in list(ds) * 2:
                    onsets.append(round(x * k / GRID) * GRID); x += d
                ds = [max(GRID, b - a) for a, b in zip(onsets, onsets[1:])][:len(ds)]
            if ps is None:  # a line in the harmony: chord tones stepping through the bars
                ps = [c for b in range(first - 1, last) for c in harmony_at(b)]
                ds = [bar_q / 3] * len(ps)
            x, end = start + (first - 1) * bar_q, start + last * bar_q
            phrase_gap = 0 if density > .7 else beat_q
            while x < end - 1e-9:
                for p, d in zip(ps, ds):
                    if x + d > end + 1e-9:
                        d = end - x
                    if d <= 1e-9:
                        break
                    # Breath between melodic notes stays on the notation grid: no 0.95-long notes and their tuplets.
                    gap = (.25 if d >= 1 else .125 if d >= .5 else 0) if role in ('melody', 'counter') else 0
                    events.append((x, d - gap, [p], (x - start) / (end - start)))
                    x += d
                if pattern == 'line' and role not in ('melody', 'counter', 'bass'):
                    continue
                x += phrase_gap
        out.append((li, layer, events))
    return out


def merge_chords(events, polyphony):
    """Overlapping events of one polyphonic player as non-overlapping chords (a held tone is re-struck
    only where the sounding set changes). More simultaneous tones than the instrument holds go to a
    second player of the same kind, if the orchestra has one."""
    if not events:
        return []
    cuts = sorted({e.at for e in events} | {e.at + e.duration for e in events})
    segments = []
    for a, b in zip(cuts, cuts[1:]):
        on = [e for e in events if e.at <= a + 1e-9 and e.at + e.duration >= b - 1e-9]
        if not on:
            continue
        pitches = tuple(sorted({p for e in on for p in e.pitches}, reverse=True))
        vel = max(e.velocity for e in on)
        tech = next((e.technique for e in on if e.technique), None)
        fresh = any(abs(e.at - a) < 1e-9 for e in on)
        if segments and not fresh and segments[-1][2] == pitches and abs(segments[-1][0] + segments[-1][1] - a) < 1e-9:
            at, dur, ps, v, t = segments[-1]
            segments[-1] = (at, dur + b - a, ps, v, t)
        else:
            segments.append((a, b - a, pitches, vel, tech))
    chunks = [[], []]
    for at, dur, ps, v, t in segments:
        chunks[0].append(Event(at, dur, ps[:polyphony], v, t))
        if len(ps) > polyphony:
            chunks[1].append(Event(at, dur, ps[polyphony:2 * polyphony], v, t))
    return [c for c in chunks if c]


def movement(plan, index):
    """Score, orchestration plan, assignment and a development report for one movement."""
    from .symphony import ORCHESTRA  # noqa: F401  (v1 shared constants live there)
    mv = plan['movements'][index]
    bpm = mv['tempo']
    slots = instruments_of(plan)
    rng = random.Random(int.from_bytes(hashlib.sha256(f"{plan['seed']}:{index}".encode()).digest()[:8]))
    lines, sections, meters, start = [], [], [], 0.
    for si, sec in enumerate(mv['sections']):
        bar_q, _ = meter(sec.get('meter', '4/4'))
        bar_q = float(bar_q)
        meters.append((start, sec.get('meter', '4/4')))
        length = bar_q * sec['bars']
        named, merged = {}, {}
        for li, layer, events in realize_section(plan, index, si, start, slots, rng):
            role = ROLES[layer['role']]
            for name in layer['instruments']:
                spec = REGISTRY[name]
                poly = spec['polyphony'] > 1
                # A chord on monophonic players is shared out among them, top to bottom; a keyboard or harp takes it whole.
                desks = 1 if poly else max(1, slots[name])
                lanes = [[] for _ in range(desks)]
                for at, dur, ps, t in events:
                    vel = velocity(layer.get('dynamic', 'mf'), t)
                    placed = sorted({place(p, name, layer.get('register')) for p in ps}, reverse=True)
                    if poly:
                        lanes[0].append(Event(at, dur, tuple(placed[:spec['polyphony']]), vel, layer.get('technique')))
                        continue
                    for d in range(desks):
                        if d < len(placed) or d == 0:
                            p = placed[d % len(placed)]
                            lanes[d].append(Event(at, dur, (p,), vel, layer.get('technique')))
                    if layer.get('octave_double') and desks > 1 and len(placed) == 1:
                        lo, hi = spec['range']
                        other = next((placed[0] + k for k in (-12, 12) if lo <= placed[0] + k <= hi), None)
                        if other is not None:
                            lanes[1].append(Event(at, dur, (other,), vel, layer.get('technique')))
                if poly:
                    merged.setdefault(name, []).extend(lanes[0])
                    named[name] = named.get(name, 0) + len(lanes[0])
                    continue
                for d, evs in enumerate(lanes):
                    if not evs:
                        continue
                    evs = tuple(e for e in evs if e.duration > 1e-6)
                    ps = [p for e in evs for p in e.pitches]
                    lines.append(Line(f'mv{index+1}:s{si+1}:l{li+1}:{name}:{d+1}', role, evs,
                                      (min(ps), max(ps)), .5, None, name))
                named[name] = named.get(name, 0) + sum(len(evs) for evs in lanes)
        for name, evs in merged.items():
            # Two hands, or a harp's two layers: everything one keyboard plays at once becomes its chords.
            for k, chunk in enumerate(merge_chords(evs, REGISTRY[name]['polyphony'])):
                ps = [p for e in chunk for p in e.pitches]
                lines.append(Line(f'mv{index+1}:s{si+1}:{name}:hands{k+1}', 'figuration', tuple(chunk),
                                  (min(ps), max(ps)), .5, None, name))
        sections.append({'role': sec['role'], 'bars': sec['bars'], 'meter': sec.get('meter', '4/4'),
                         'mode': sec.get('mode', mv.get('mode', 'major')),
                         'progression': sec.get('progression', [1]),
                         'start_quarters': start, 'end_quarters': start + length,
                         'start_seconds': start * 60 / bpm, 'duration_seconds': length * 60 / bpm,
                         'sounding': named, 'tacet': sorted(set(slots) - set(named))})
        start += length
    op = {'title': f"{plan['title']} — {index+1}. {mv['title']}", 'ensemble': plan['orchestra'],
          'tempo': bpm, 'duration': start * 60 / bpm, 'school': 'symphony', 'audio_profile': 'native_sfz',
          'meters': meters, 'held_swell': bool(plan.get('held_swell', False))}
    score, assignment = orchestrate(lines, op)
    from music21 import dynamics, expressions
    # Dynamics at changes, technique names at first use: the same notation hygiene as grammar v1.
    for part in score.parts:
        last = {}
        for item in list(part.recurse()):
            if isinstance(item, dynamics.Dynamic):
                kind, value = 'dynamic', item.value
            elif isinstance(item, expressions.TextExpression):
                kind, value = 'technique', item.content
            else:
                continue
            if last.get(kind) == value:
                item.activeSite.remove(item)
            else:
                last[kind] = value
    return score, op, assignment, {'grammar': 2, 'sections': sections, 'seconds': op['duration'],
                                   'bars': sum(s['bars'] for s in mv['sections']), 'tempo': bpm}


def example():
    """A complete v2 plan the composer sees as a contract example: waltz, march, chorale, silence, row."""
    orchestra = ([{'instrument': n, 'count': c} for n, c in
                  [('piccolo', 1), ('flute', 2), ('oboe', 2), ('clarinet', 2), ('bassoon', 2), ('horn', 4),
                   ('trumpet', 3), ('trombone', 2), ('bass_trombone', 1), ('tuba', 1), ('timpani', 1),
                   ('snare', 1), ('bass_drum', 1), ('cymbals', 1), ('harp', 1)]] +
                 [{'instrument': n, 'players': c, 'divisi': 2} for n, c in
                  [('violin_1_section', 16), ('violin_2_section', 14), ('viola_section', 12),
                   ('cello_section', 10), ('bass_section', 8)]])
    waltz = {'pitches': [67, 71, 74, 72, 71, 69], 'durations': [1, 1, 1, 1.5, .5, 3],
             'source': {'kind': 'composed', 'note': 'the third phrase of a remembered waltz'}}
    L = lambda inst, role, **k: {'instruments': inst, 'role': role, **k}
    first = [
        {'role': 'opening', 'bars': 48, 'meter': '3/4', 'theme': 'waltz', 'progression': [1, 4, 5, 1],
         'harmonic_rhythm': 2, 'layers': [
            L(['clarinet'], 'melody', material='theme:waltz', dynamic='p'),
            L(['cello_section'], 'bass', pattern='waltz', dynamic='pp', technique='pizzicato'),
            L(['viola_section', 'violin_2_section'], 'pad', pattern='waltz', dynamic='pp', technique='pizzicato')]},
        {'role': 'growth', 'bars': 32, 'meter': '2/4', 'transform': 'fragmentation', 'mode': 'mixolydian',
         'progression': [1, 5], 'layers': [
            L(['trumpet'], 'melody', material='theme:waltz', dynamic=['mf', 'f']),
            L(['snare'], 'percussion', pattern='rolls', density=.4, dynamic='mf'),
            L(['tuba', 'bass_section'], 'bass', pattern='march', dynamic='mf'),
            L(['horn'], 'pad', pattern='offbeat', dynamic='mp')]},
        {'role': 'transformation', 'bars': 40, 'meter': '3/4', 'transform': 'inversion', 'mode': 'minor',
         'progression': [1, 6, 4, 5], 'layers': [
            L(['violin_1_section'], 'melody', material='theme:waltz', dynamic=['p', 'ff']),
            L(['flute', 'oboe'], 'points', material='row:crowd', pattern='points', density=.5, dynamic='mp'),
            L(['cello_section', 'bass_section'], 'bass', pattern='waltz', dynamic='mf'),
            L(['viola_section'], 'pad', pattern='tremolo', dynamic=['p', 'f'])]},
        {'role': 'climax', 'bars': 24, 'meter': '3/4', 'progression': [1, 4, -5, 1], 'layers': [
            L(['trumpet', 'violin_1_section'], 'melody', material='theme:waltz', dynamic='ff'),
            L(['trombone', 'bass_trombone', 'horn'], 'pad', pattern='hits', density=.8, dynamic='f'),
            L(['timpani', 'tuba'], 'bass', pattern='waltz', dynamic='f'),
            L(['bass_drum', 'cymbals'], 'percussion', pattern='hits', density=.5, dynamic='f')]},
        {'role': 'dissolution', 'bars': 24, 'meter': '3/4', 'transform': 'augmentation',
         'progression': [1], 'layers': [
            L(['harp'], 'figuration', pattern='arpeggio', dynamic='pp', bars=[1, 16]),
            L(['clarinet'], 'melody', material='theme:waltz', dynamic='pp', bars=[5, 24])]}]
    slow = [
        {'role': 'A', 'bars': 24, 'meter': '4/4', 'mode': 'dorian', 'progression': [1, 7, 4, 1], 'harmonic_rhythm': 2,
         'theme': 'waltz', 'transform': 'augmentation', 'layers': [
            L(['horn'], 'chorale', pattern='sustain', dynamic='p'),
            L(['cello_section'], 'melody', material='theme:waltz', dynamic='mp')]},
        {'role': 'B', 'bars': 20, 'meter': '5/4', 'progression': [1, 2], 'layers': [
            L(['oboe'], 'melody', material='theme:waltz', transform='retrograde', dynamic='mp'),
            L(['harp'], 'figuration', pattern='arpeggio', dynamic='pp'),
            L(['bass_section'], 'drone', pattern='sustain', dynamic='pp')]},
        {'role': 'C', 'bars': 8, 'meter': '4/4', 'layers': []},
        {'role': 'B_return', 'bars': 20, 'meter': '5/4', 'progression': [1, 2], 'layers': [
            L(['flute'], 'melody', material='theme:waltz', transform='inversion', dynamic='p'),
            L(['violin_2_section', 'viola_section'], 'pad', pattern='sustain', dynamic='pp')]},
        {'role': 'A_return', 'bars': 24, 'meter': '4/4', 'mode': 'dorian', 'progression': [1, 7, 4, 1],
         'harmonic_rhythm': 2, 'layers': [
            L(['violin_1_section'], 'melody', material='theme:waltz', transform='augmentation', dynamic='pp'),
            L(['horn'], 'chorale', pattern='sustain', dynamic='pp')]}]
    finale = [{'role': r, 'bars': b, 'meter': m, 'progression': pr, 'transform': tr, 'layers': ls}
              for r, b, m, pr, tr, ls in [
        ('refrain', 32, '2/4', [1, 5], 'identity', [
            L(['piccolo', 'flute'], 'melody', material='theme:waltz', dynamic='f', octave_double=True),
            L(['snare'], 'percussion', pattern='rolls', density=.6, dynamic='mf'),
            L(['tuba', 'bassoon'], 'bass', pattern='march', dynamic='f'),
            L(['horn', 'clarinet'], 'pad', pattern='offbeat', dynamic='mf')]),
        ('episode', 40, '7/8', [1, 3, 4], 'fragmentation', [
            L(['viola_section'], 'ostinato', material='school:additive', pattern='ostinato', dynamic='mp'),
            L(['clarinet'], 'melody', material='theme:waltz', dynamic='mf')]),
        ('refrain', 32, '2/4', [1, 5], 'diminution', [
            L(['trumpet'], 'melody', material='theme:waltz', dynamic='f'),
            L(['bass_section', 'tuba'], 'bass', pattern='march', dynamic='f'),
            L(['snare', 'cymbals'], 'percussion', pattern='hits', density=.4, dynamic='f')]),
        ('episode', 40, '3/4', [1, 6, 4, 5], 'inversion', [
            L(['oboe'], 'melody', material='theme:waltz', dynamic='mp'),
            L(['cello_section'], 'bass', pattern='walking', dynamic='p', technique='pizzicato')]),
        ('refrain', 32, '2/4', [1, 4, 5, 1], 'identity', [
            L(['trumpet', 'violin_1_section'], 'melody', material='theme:waltz', dynamic='ff'),
            L(['trombone', 'bass_trombone'], 'pad', pattern='hits', density=.7, dynamic='ff'),
            L(['timpani', 'tuba', 'bass_section'], 'bass', pattern='march', dynamic='ff'),
            L(['bass_drum', 'cymbals', 'snare'], 'percussion', pattern='rolls', density=.5, dynamic='f')]),
        ('coda', 16, '3/4', [1], 'augmentation', [
            L(['clarinet'], 'melody', material='theme:waltz', dynamic=['p', 'ppp'])])]]
    return {'version': 2, 'title': 'The third phrase', 'seed': 7,
            'concept': 'A waltz half-remembered is crowded out by a march and returns slower, with room around it.',
            'method': 'Cyclic waltz cell; meter as conflict (3/4 against 2/4 and 7/8); a twelve-tone crowd of points.',
            'orchestra': orchestra, 'themes': {'waltz': waltz},
            'rows': {'crowd': [0, 11, 3, 4, 8, 7, 9, 5, 6, 1, 2, 10]},
            'movements': [
                {'title': 'The waltz', 'character': 'remembered, then crowded', 'form': 'through-composed',
                 'tempo': 66, 'centre': 55, 'mode': 'major', 'sections': first},
                {'title': 'Room', 'character': 'slow, with a silence at its centre', 'form': 'arch', 'tempo': 50,
                 'centre': 50, 'mode': 'dorian', 'sections': slow},
                {'title': 'Crowd and waltz', 'character': 'a march that cannot hold', 'form': 'rondo', 'tempo': 104,
                 'centre': 55, 'mode': 'major', 'sections': finale}]}
