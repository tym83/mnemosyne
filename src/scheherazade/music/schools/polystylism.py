"""Archived atelier quotation collides with a displaced chromatic layer."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    quotation = plan.get('quotation')
    if not quotation or not quotation.get('events') or not quotation.get('sha256'):
        raise ValueError('polystylism requires archived quotation events and source SHA-256')
    score, rng, sections, total = setup(plan, seed, 'polystylism', choices=choices)
    shift = rng.choice([0, 2, 5])
    period = quotation['quarters']
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            old = i == len(score.parts)-1
            mark(part, start, 'Atelier nocturne quotation' if old else 'Chromatic interruption', 'p' if old else 'ff')
            at = start
            if old:
                while at < end:
                    for offset, length, pitch in quotation['events']:
                        onset = at+offset
                        if onset < end:
                            put(part, onset, min(length, end-onset), fit(pitch, name, sec))
                    at += period
            else:
                at += 4 if s == 0 else i*.25
                j = 0
                while at < end:
                    pitch = 60+shift+(j*5+i) % 12
                    put(part, at, min(.5, end-at), fit(pitch, name, sec))
                    at += [3, .75, 1.25][s % 3]
                    j += 1
    return finish(score, total)
