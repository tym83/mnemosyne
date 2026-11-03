"""Hammered chromatic blocks against stark unisons and ascetic repetitions."""
from music21 import articulations
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'ustvolskaya', choices=choices)
    centre = rng.choice([60, 62, 65])
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, 'Hammered block' if s % 2 == 0 else 'Stark unison', 'fff' if s % 2 == 0 else 'ppp')
            at = start
            while at < end:
                pitch = fit(centre + (i % 4 if s % 2 == 0 else 0), name, sec)
                if name == 'piano' and s % 2 == 0:
                    pitch = [fit(centre+k, name, sec) for k in range(6)]
                put(part, at, min(.5, end-at), pitch, articulations.Accent())
                at += 2 if s % 2 == 0 else 4
    return finish(score, total)
