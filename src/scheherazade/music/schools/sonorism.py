"""Quarter-tone bands and parallel glissando fields, with synthetic bow techniques."""
from music21 import spanner
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'sonorism', choices=choices)
    centre = rng.choice([60, 62, 64])
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, ['sul ponticello', 'col legno', 'bow pressure'][s % 3] + '; measured time field')
            at = start
            while at < end:
                length = min(6, end-at)
                pitch = fit(centre + i*.5, name, sec)
                n = put(part, at, length/2, pitch)
                target = fit(pitch + (2 if s % 2 else -2), name, sec)
                m = put(part, at+length/2, length/2, target)
                part.insert(at, spanner.Glissando(n, m, lineType='solid'))
                at += length + rng.choice([0, 1, 2])
    return finish(score, total)
