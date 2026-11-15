"""Symphony grammar v2: the plan is the score's skeleton, and nothing sounds that the plan does not name.

v1 wrote one fixed texture (4/4, the same root cycle, constant harp figuration) whatever the plan said.
v2 realizes what the composer writes: meter per section, mode and harmonic progression, and layers.
A layer names its instruments, role, material, accompaniment pattern, dynamic and register. An
instrument that no layer of a section names is silent there. Unknown plan fields are rejected, so the
composer always knows what is realized. Tempo is per movement and a section may set its own (`tempo`),
or change it gradually across its length (`tempo_to`, one step per quarter note); meter may change per
section.
"""
from dataclasses import replace
from fractions import Fraction
import hashlib
import math
import random

from .instrumentarium import REGISTRY, audio_ensemble
from .orchestration import Event, Line, orchestrate
from . import tempo_map

MODES = {
    'major': [0, 2, 4, 5, 7, 9, 11], 'minor': [0, 2, 3, 5, 7, 8, 10], 'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'dorian': [0, 2, 3, 5, 7, 9, 10], 'phrygian': [0, 1, 3, 5, 7, 8, 10], 'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10], 'locrian': [0, 1, 3, 5, 6, 8, 10],
    'pentatonic': [0, 2, 4, 7, 9], 'minor_pentatonic': [0, 3, 5, 7, 10], 'whole_tone': [0, 2, 4, 6, 8, 10],
    'octatonic': [0, 1, 3, 4, 6, 7, 9, 10], 'hijaz': [0, 1, 4, 5, 7, 8, 10], 'chromatic': list(range(12)),
}
DYNAMICS = {'ppp': 24, 'pp': 36, 'p': 48, 'mp': 60, 'mf': 72, 'f': 88, 'ff': 104, 'fff': 118}
def line_role(role, instrument):
    # Pitched percussion in a percussion layer plays its pitches as figuration.
    if role == 'percussion' and not REGISTRY[instrument].get('unpitched'):
        return 'figuration'
    return ROLES[role]


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
SECTION_KEYS = {'role', 'bars', 'meter', 'tempo', 'tempo_to', 'theme', 'transform', 'shift', 'mode', 'progression',
                'harmonic_rhythm', 'layers', 'schools', 'notes'}
LAYER_KEYS = {'instruments', 'role', 'material', 'transform', 'pattern', 'dynamic', 'register', 'density',
              'technique', 'bars', 'octave_double', 'time_scale', 'repeat', 'offset', 'rest_between', 'notes'}
PLAN_LIMIT = 100_000  # characters of JSON: a plan the composer can write out whole in one answer
GRID = .25  # onsets of a time-scaled line fall on a sixteenth grid; the ratio holds over a phrase


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


def section_tempo(mv, sec):
    """(tempo, tempo_to or None) of a section; the movement tempo is the default."""
    start = sec.get('tempo', mv['tempo'])
    to = sec.get('tempo_to')
    return start, (None if to is None or to == start else to)


def instruments_of(plan):
    players = audio_ensemble(plan['orchestra'])
    slots = {}
    for p in players:
        slots[p.instrument] = slots.get(p.instrument, 0) + p.divisi
    return slots


def validate(plan, *, study=False):
    """Check a plan and return its length in seconds. A theme without `source` gets {'kind': 'composed'}."""
    from .schools import SCHOOLS
    import json
    size = len(json.dumps(plan, ensure_ascii=False))
    if size > PLAN_LIMIT:
        raise ValueError(f'plan is {size} characters; the limit is {PLAN_LIMIT}. Write it compactly: at most 12 '
                         'layers per section, one layer per idea (repeat, bars and several instruments in one layer '
                         'instead of copies), notes of one sentence')
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
            theme['source'] = {'kind': 'composed'}
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
        # A named form whose roles differ (or an unknown form name) is a free form: roles are the composer's.
        if not secs or any(not isinstance(s.get('role'), str) or not s['role'] for s in secs):
            raise ValueError(f'{where}: name every section role (a short word: "exposition", "A", "storm"…)')
        used = set()
        quarters = Fraction(0)
        for si, sec in enumerate(secs):
            sw = f'{where} section {si+1} ({sec.get("role")})'
            strict(sec, SECTION_KEYS, sw)
            if type(sec.get('bars')) is not int or sec['bars'] < 1:
                raise ValueError(f'{sw}: whole bars required')
            bar, _ = meter(sec.get('meter', '4/4'))
            quarters += bar * sec['bars']
            for key in ('tempo', 'tempo_to'):
                if key in sec and (not finite(sec[key]) or not 30 <= sec[key] <= 240):
                    raise ValueError(f'{sw}: {key} 30–240 (quarter notes per minute)')
            seconds += tempo_map.section_seconds(float(bar * sec['bars']), *section_tempo(mv, sec))
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
                if unpitched and layer['role'] != 'percussion':
                    raise ValueError(f'{lw}: unpitched {unpitched} need role "percussion" '
                                     '(pitched instruments may share that layer)')
                tech = layer.get('technique')
                if tech in TECHNIQUES:
                    lacking = [n for n in names if realized_technique(tech, n) is None]
                    if lacking:
                        raise ValueError(f'{lw}: technique {tech} changes the sound and has no samples for {lacking}; '
                                         'available: ' + '; '.join(f'{n}: {sorted(techniques(n))}' for n in lacking))
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
                if type(layer.get('repeat', 1)) is not int or layer.get('repeat', 1) < 0:
                    raise ValueError(f'{lw}: repeat = how many statements of the line (0 = until its bars end)')
                for key in ('offset', 'rest_between'):
                    v = layer.get(key, 0)
                    if not finite(v) or v < 0 or v * 8 != int(v * 8):
                        raise ValueError(f'{lw}: {key} in quarters, ≥ 0, multiple of 0.125')
                scale_t = layer.get('time_scale', 1)
                if not finite(scale_t) or not .25 <= scale_t <= 4:
                    raise ValueError(f'{lw}: time_scale in [0.25, 4] (duration multiplier: 1.414 = this voice at 1/√2 tempo)')
                span = layer.get('bars')
                if span is not None and (len(span) != 2 or not all(type(x) is int for x in span)
                                         or not 1 <= span[0] <= span[1] <= sec['bars']):
                    raise ValueError(f'{lw}: bars [first, last] inside the section (1-based)')
                sounding.update(names)
        heard.append(used)
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


def techniques(instrument):
    """Playing techniques with samples for this instrument (sustain/arco is the plain sound)."""
    spec = REGISTRY[instrument]
    names = set(spec['samples'].get('patches', {})) | set(spec['samples'].get('key_ranges', {}))
    return names | {'arco' if spec['family'] == 'strings' else 'sustain'}


def realized_technique(tech, instrument):
    """(technique for the event, shortened) as an instrument realizes a layer technique, or None if it cannot.

    arco and sustain are the plain sound of every instrument; staccato without its own samples is a
    shortened plain note. Other techniques change the sound and need samples."""
    if not tech or tech in ('arco', 'sustain'):
        return None, False
    if tech == 'staccato' and REGISTRY[instrument]['family'] in ('keyboard', 'plucked', 'percussion'):
        return 'staccato', False  # orchestration plays a struck staccato as its plain, naturally short sound
    if tech in techniques(instrument):
        return tech, False
    if tech == 'staccato':
        return None, True
    return None


def playable(instrument):
    """Sounding span an instrument really plays here: its range met by its sampled keys."""
    spec = REGISTRY[instrument]
    technique = 'arco' if spec['family'] == 'strings' else 'sustain'
    zones = spec['samples'].get('key_ranges', {}).get(technique, [spec['range']])
    lo = max(spec['range'][0], min(a for a, _ in zones))
    hi = min(spec['range'][1], max(b for _, b in zones))
    return lo, hi


def place(pitch, instrument, register=None, technique=None):
    """The octave of pitch class `pitch` nearest to the register's centre, playable and sampled
    (in the zones of `technique` when it has its own)."""
    spec = REGISTRY[instrument]
    if spec.get('unpitched'):
        return spec['comfortable'][0]
    if spec['family'] in ('keyboard', 'plucked', 'percussion'):
        # Fixed-pitch instruments play no quarter tones (and a MIDI chord cannot bend its notes apart).
        pitch = round(pitch)
    lo, hi = register or spec['comfortable']
    if register and lo <= pitch <= hi and spec['range'][0] <= pitch <= spec['range'][1]:
        return pitch  # a written pitch inside its register stays where the composer put it
    target = (lo + hi) / 2 if register else pitch
    plain = 'arco' if spec['family'] == 'strings' else 'sustain'
    ranges = spec['samples'].get('key_ranges', {})
    zones = ranges.get(technique) or ranges.get(plain, [spec['range']])
    options = [pitch + 12 * k for k in range(-10, 11)
               if spec['range'][0] <= pitch + 12 * k <= spec['range'][1]
               and any(a <= round(pitch + 12 * k) <= b for a, b in zones)]
    if not options:
        lo_p, hi_p = playable(instrument)
        raise ValueError(f'{instrument} plays sounding MIDI {lo_p}–{hi_p} with the available samples; '
                         f'pitch class of {pitch} has no octave there')
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
        # Themes sound at the pitches the composer wrote; only an explicit section shift transposes them.
        ps = [p + shift for p in theme['pitches']]
        ps, ds = transform(ps, theme['durations'], layer.get('transform', sec.get('transform', 'identity')))
        return ps, ds
    if kind == 'notagen':
        m = plan['notagen_material']
        return [p + shift for p in m['pitches']], list(m['durations'])
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
                # Held tones are the layer's own material when it has one (a one-note theme holds that note),
                # otherwise the chord; a tone is held on while the sounding set stays the same.
                held = sorted(set(stream_ps)) if stream_ps else ch
                tones = held if role in ('pad', 'chorale', 'drone') else [held[0]]
                if events and events[-1][2] == tones and abs(events[-1][0] + events[-1][1] - a) < 1e-9:
                    events[-1] = (events[-1][0], events[-1][1] + bar_q, tones, events[-1][3])
                else:
                    events.append((a + (layer.get('offset', 0) if b == first - 1 else 0),
                                   bar_q - (layer.get('offset', 0) if b == first - 1 else 0), tones, t))
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
            x, end = start + (first - 1) * bar_q + layer.get('offset', 0), start + last * bar_q
            # A line is stated `repeat` times (0: again and again to the end of its bars), then the layer is silent.
            times = layer.get('repeat', 1) or math.inf
            done = 0
            while x < end - 1e-9 and done < times:
                done += 1
                for p, d in zip(ps, ds):
                    if x + d > end + 1e-9:
                        d = end - x
                    if d <= 1e-9:
                        break
                    # Written at full value: breath and phrasing belong to the performer (and the renderer), not to
                    # shortened notation, which only produced dotted-dotted values and tuplets.
                    events.append((x, d, [p], (x - start) / (end - start)))
                    x += d
                x += layer.get('rest_between', 0)
        out.append((li, layer, events))
    return out


def note_adjustment(adjusted, name, kind, count=1):
    """Record what the realization had to change so a plan would play (shown in the development report)."""
    entry = adjusted.setdefault(name, {})
    entry[kind] = entry.get(kind, 0) + count


def lane_ids(plan):
    """Orchestration lane ids of every instrument, in the order orchestration builds them."""
    out = {}
    for p in audio_ensemble(plan['orchestra']):
        for div in range(p.divisi):
            out.setdefault(p.instrument, []).append(p.id + (f'-div{div+1}' if p.divisi > 1 else ''))
    return out


def share_desks(items, desks, adjusted, name):
    """Give every event of one monophonic instrument a desk on which it overlaps nothing.

    An event keeps its own desk when that desk is free, else takes another free one. When all are busy,
    the note sounding on its desk is cut at the new onset; a note that starts together with notes on every
    desk is left out. Both are recorded."""
    lanes = [[] for _ in range(desks)]
    out = []
    for item in sorted(items, key=lambda x: x[0]):
        at, d = item[0], item[5]
        order = [d] + [k for k in range(desks) if k != d]
        free = next((k for k in order if not lanes[k] or lanes[k][-1][0] + lanes[k][-1][1] <= at + 1e-9), None)
        if free is None:
            free = next((k for k in order if lanes[k][-1][0] < at - 1e-9), None)
            if free is None:
                note_adjustment(adjusted, name, 'dropped')
                continue
            lanes[free][-1][1] = at - lanes[free][-1][0]
            note_adjustment(adjusted, name, 'truncated')
        item[5] = free
        lanes[free].append(item)
        out.append(item)
    return out


def merge_chords(events, polyphony, players=2, adjusted=None, name=None):
    """Overlapping events of one polyphonic player as non-overlapping chords (a held tone is re-struck
    only where the sounding set changes). More simultaneous tones than the instrument holds go to a
    second player of the same kind, if the orchestra has one; otherwise the outer tones sound and the
    inner ones are left out (recorded)."""
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
        if len(ps) > polyphony and players < 2:
            if adjusted is not None:
                note_adjustment(adjusted, name, 'chord_tones_dropped', len(ps) - polyphony)
            ps = ps[:polyphony - 1] + ps[-1:]
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
    desk_of = {}  # line id -> (instrument, desk): the lane a line keeps if free assignment cannot place it
    steps, words = [], []  # the tempo map: (quarter, bpm, shown); rit./accel. words
    for sec in mv['sections']:
        length = float(meter(sec.get('meter', '4/4'))[0]) * sec['bars']
        a, b = section_tempo(mv, sec)
        for step in tempo_map.section_steps(start, length, a, b):
            if not steps or steps[-1][1] != step[1]:
                steps.append(step)
        if b is not None and len(tempo_map.section_steps(start, length, a, b)) > 1:
            words.append((start, 'rit.' if b < a else 'accel.'))
        start += length
    total = start
    changing = len(steps) > 1
    base = bpm if steps[0][1] == bpm else steps[0][1]  # every section may share one tempo of its own
    timing = {'tempo': base, 'tempo_map': [list(x) for x in steps], 'quarters': total}

    def clock(q):
        return tempo_map.seconds_at(timing, q) if changing else q * 60 / base

    start = 0.
    for si, sec in enumerate(mv['sections']):
        bar_q, _ = meter(sec.get('meter', '4/4'))
        bar_q = float(bar_q)
        if not meters or meters[-1][1] != sec.get('meter', '4/4'):
            meters.append((start, sec.get('meter', '4/4')))
        length = bar_q * sec['bars']
        named, merged = {}, {}
        adjusted = {}
        pending = {}  # monophonic instrument -> its events from every layer, to share out among its desks
        in_section = {n for l in sec.get('layers', []) for n in l['instruments']}
        for li, layer, events in realize_section(plan, index, si, start, slots, rng):
            low_first = layer['role'] in ('bass', 'drone')
            mono = [(pos, n) for pos, n in enumerate(layer['instruments']) if REGISTRY[n]['polyphony'] <= 1
                    and not REGISTRY[n].get('unpitched')]
            families = {REGISTRY[n]['family'] for _, n in mono}
            # Players of the same family who are silent in this section can take tones nobody else can play.
            spare = [n for n in slots if n not in in_section and REGISTRY[n]['family'] in families
                     and REGISTRY[n]['polyphony'] <= 1 and not REGISTRY[n].get('unpitched')]
            for pos, name in enumerate(layer['instruments']):
                spec = REGISTRY[name]
                if (pos, name) in mono:
                    continue
                technique, short = realized_technique(layer.get('technique'), name)
                for at, dur, ps, t in events:
                    vel = velocity(layer.get('dynamic', 'mf'), t)
                    if short:
                        dur = min(dur, on_grid(dur * .5))
                    placed = sorted({place(p, name, layer.get('register'), technique) for p in ps}, reverse=not low_first)
                    if spec['polyphony'] > 1:
                        merged.setdefault(name, []).append(Event(at, dur, tuple(placed[:spec['polyphony']]), vel, technique))
                        named[name] = named.get(name, 0) + 1
                    else:  # unpitched
                        pending.setdefault(name, []).append([at, dur, placed[0], vel, technique, 0, (li, pos), line_role(layer['role'], name)])
            if not mono:
                continue
            # Every monophonic desk of the layer, instrument by instrument; then the spare players of the family.
            desks = [(pos, n, d) for pos, n in mono for d in range(max(1, slots[n]))]
            extra = [(len(layer['instruments']) + k, n, d) for k, n in enumerate(spare) for d in range(max(1, slots[n]))]
            for at, dur, ps, t in events:
                vel = velocity(layer.get('dynamic', 'mf'), t)
                tones = sorted(set(ps), reverse=not low_first)
                fewest = min(max(1, slots[n]) for _, n in mono)
                if len(tones) <= fewest:
                    # Every instrument of the layer doubles the chord on its own desks.
                    assignment = [(pos, n, d, tones[d]) for pos, n in mono for d in range(max(1, slots[n]))
                                  if d < len(tones)]
                else:
                    # A chord wider than an instrument: its tones are spread over all the layer's desks, then
                    # over silent players of the same family; only what nobody can hold is left out.
                    targets = desks + extra
                    assignment = [(pos, n, d, tones[k]) for k, (pos, n, d) in enumerate(targets) if k < len(tones)]
                    for pos, n, d, _ in assignment:
                        if (pos, n, d) in extra:
                            note_adjustment(adjusted, n, 'took_chord_tone')
                    if len(tones) > len(targets):
                        note_adjustment(adjusted, mono[0][1], 'chord_tones_dropped', len(tones) - len(targets))
                for pos, name, d, tone in assignment:
                    technique, short = realized_technique(layer.get('technique'), name)
                    held = min(dur, on_grid(dur * .5)) if short else dur
                    p = place(tone, name, layer.get('register'), technique)
                    pending.setdefault(name, []).append([at, held, p, vel, technique, d, (li, pos),
                                                         line_role(layer['role'], name)])
                if layer.get('octave_double') and len(tones) == 1:
                    pos, name = mono[0]
                    if slots[name] > 1:
                        lo, hi = REGISTRY[name]['range']
                        first = place(tones[0], name, layer.get('register'))
                        other = next((first + k for k in (-12, 12) if lo <= first + k <= hi), None)
                        if other is not None:
                            pending.setdefault(name, []).append([at, dur, other, vel, None, 1, (li, pos),
                                                                 line_role(layer['role'], name)])
        grouped = {}
        for name, items in pending.items():
            for item in share_desks(items, max(1, slots[name]), adjusted, name):
                at, dur, p, vel, technique, d, key, role = item
                grouped.setdefault((key, d), (name, role, []))[2].append(Event(at, dur, (p,), vel, technique))
                named[name] = named.get(name, 0) + 1
        for ((li, _), d), (name, role, evs) in sorted(grouped.items(), key=lambda x: x[0]):
            evs = tuple(e for e in sorted(evs, key=lambda e: e.at) if e.duration > 1e-6)
            if not evs:
                continue
            ps = [p for e in evs for p in e.pitches]
            lines.append(Line(f'mv{index+1}:s{si+1}:l{li+1}:{name}:{d+1}', role, evs,
                              (min(ps), max(ps)), .5, None, name))
            desk_of[lines[-1].id] = (name, d)
        for name, evs in merged.items():
            # Two hands, or a harp's two layers: everything one keyboard plays at once becomes its chords.
            for k, chunk in enumerate(merge_chords(evs, REGISTRY[name]['polyphony'], slots[name], adjusted, name)):
                ps = [p for e in chunk for p in e.pitches]
                lines.append(Line(f'mv{index+1}:s{si+1}:{name}:hands{k+1}', 'figuration', tuple(chunk),
                                  (min(ps), max(ps)), .5, None, name))
                desk_of[lines[-1].id] = (name, k)
        sections.append({'role': sec['role'], 'bars': sec['bars'], 'meter': sec.get('meter', '4/4'),
                         'mode': sec.get('mode', mv.get('mode', 'major')),
                         'progression': sec.get('progression', [1]),
                         'start_quarters': start, 'end_quarters': start + length,
                         'start_seconds': clock(start), 'duration_seconds': clock(start + length) - clock(start) if changing else length * 60 / base,
                         'sounding': named, 'tacet': sorted(set(slots) - set(named)),
                         **({'tempo': section_tempo(mv, sec)[0]} if 'tempo' in sec else {}),
                         **({'tempo_to': section_tempo(mv, sec)[1]} if section_tempo(mv, sec)[1] is not None else {}),
                         **({'adjusted': adjusted} if adjusted else {})})
        start += length
    op = {'title': f"{plan['title']} — {index+1}. {mv['title']}", 'ensemble': plan['orchestra'],
          'tempo': base, 'duration': start * 60 / base, 'school': 'symphony', 'audio_profile': 'native_sfz',
          'meters': meters, 'held_swell': bool(plan.get('held_swell', False))}
    if changing:
        # Score time stays in quarters; the renderer and the score's marks follow the map.
        op.update(duration=clock(total), quarters=total,
                  tempo_map=[list(x) for x in steps], tempo_text=[list(w) for w in words])
    try:
        score, assignment = orchestrate(lines, op)
    except ValueError as exc:
        if 'No playable available player' not in str(exc):
            raise
        # Free assignment can split a line between desks and then find no desk for the next one; the desks
        # were already shared out without overlap, so each line keeps its own.
        lanes = lane_ids(plan)
        pinned = [replace(line, lane=lanes[desk_of[line.id][0]][desk_of[line.id][1]]) for line in lines]
        score, assignment = orchestrate(pinned, op)
    from music21 import dynamics, expressions, metadata
    # The work's title above, the movement's below: music21 otherwise writes one long title twice.
    score.metadata = metadata.Metadata()
    score.metadata.title = plan['title']
    score.metadata.movementName = f"{index+1}. {mv['title']}"
    from music21 import dynamics, expressions
    # Dynamics at changes, technique names at first use: the same notation hygiene as grammar v1.
    for part in score.parts:
        last = {}
        for item in list(part.recurse()):
            if isinstance(item, dynamics.Dynamic):
                kind, value = 'dynamic', item.value
            elif isinstance(item, expressions.TextExpression):
                if item.content in ('rit.', 'accel.'):
                    continue
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
    L = lambda inst, role, **k: {'instruments': inst, 'role': role, **({'repeat': 0} if k.get('material', '').startswith('theme:') else {}), **k}
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
