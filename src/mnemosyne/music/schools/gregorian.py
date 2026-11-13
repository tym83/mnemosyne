"""Plainchant in one of eight church modes: psalm-tone recitation, neumes and melismas over an ison."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish
from .chant import MODES, WHITE, degree_pitch, place_final, walk
from .material import mark

EIGHTH = .5


def kind(sec):
    if sec['character'] == 'still' or sec['density'] < .45:
        return 'psalm'
    if sec['character'] == 'luminous' or sec['density'] >= .75:
        return 'melismatic'
    return 'neumatic'


def psalm_tone(rng, tenor, lo, hi):
    """Intonation, recitation, mediant, recitation, termination on the final."""
    tenor = max(lo, min(hi, tenor))
    notes = [(max(lo, tenor-2), EIGHTH), (max(lo, tenor-1), EIGHTH), (tenor, 1)]
    for _ in range(rng.randrange(5, 11)):
        notes.append((tenor, 1 if rng.random() < .2 else EIGHTH))
    notes += [(min(hi, tenor+1), EIGHTH), (tenor, EIGHTH), (max(lo, tenor-1), 1.5)]
    notes.append((None, EIGHTH))
    for _ in range(rng.randrange(4, 9)):
        notes.append((tenor, 1 if rng.random() < .2 else EIGHTH))
    descent = list(range(tenor-1, 0, -1)) if tenor > 0 else []
    notes += [(d, EIGHTH) for d in descent] + [(0, 1.5)]
    return notes


def neumes(rng, start, end, lo, hi, melismatic):
    """Syllables of 1-3 eighths (melismas 4-8); word ends lengthen to a quarter."""
    groups = []
    for _ in range(rng.randrange(6, 13)):
        size = rng.randrange(4, 9) if melismatic and rng.random() < .35 else rng.randrange(1, 4)
        groups.append(size)
    degrees = walk(rng, sum(groups), lo, hi, start=max(lo, min(hi, start)), end=max(lo, min(hi, end)))
    notes, k = [], 0
    for g, size in enumerate(groups):
        word_end = g == len(groups)-1 or rng.random() < .35
        for j in range(size):
            last = j == size-1
            notes.append((degrees[k], 1.5 if g == len(groups)-1 and last else 1 if word_end and last else EIGHTH))
            k += 1
    return notes


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score, rng, sections, total = setup(plan, seed, 'gregorian', choices=choices)
    mode = MODES[rng.randrange(8)]
    names = ENSEMBLES[plan['ensemble']]
    ison = len(names)-1
    singers = list(range(ison))
    tenor = (WHITE.index(mode['tenor']) - WHITE.index(mode['final'])) % 7
    phrase = 0
    for start, end, sec in sections:
        finals = {i: place_final(mode['final'], *mode['ambitus'], *limits(names[i], sec)) for i in singers}
        lo = max(f[1] for f in finals.values())
        hi = min(f[2] for f in finals.values())
        ilow, ihigh = limits(names[ison], sec)
        drone = next(p for p in range(ilow, ihigh+1) if p % 12 == mode['final'])
        for i in range(len(names)):
            mark(score.parts[i], start, f"Mode {mode['number']} ({mode['name']}); {kind(sec)}; "
                 + ('ison on the final' if i == ison else 'unison chant'))
        at = start
        while at < end:
            style = kind(sec)
            if style == 'psalm':
                notes = psalm_tone(rng, tenor, lo, hi)
            else:
                notes = neumes(rng, rng.choice([0, tenor]), rng.choice([0, 0, tenor]), lo, hi, style == 'melismatic')
            length = sum(n[1] for n in notes)
            if at+length > end:
                # A phrase that does not fit is not cut: the final is held to the section end.
                notes = [(0, end-at)]
                length = end-at
            voices = [0] if phrase % 2 == 0 else singers
            cursor = at
            for degree, dur in notes:
                if degree is not None:
                    for i in voices:
                        put(score.parts[i], cursor, dur, degree_pitch(finals[i][0], degree))
                cursor += dur
            sung = length - sum(d for g, d in notes[-1:] if g is None)
            put(score.parts[ison], at, sung, drone)
            phrase += 1
            at += length + (EIGHTH if at+length+EIGHTH <= end else 0)
    score.editorial.mode = mode
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Mode, neume groups and ison remain fixed; the swell of each syllable is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
