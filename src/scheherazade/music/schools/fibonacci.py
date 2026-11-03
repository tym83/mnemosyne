"""Fibonacci formal boundaries; Fibonacci/Lucas rhythm, diatonic/chromatic opposition."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark

FIBONACCI = (1, 1, 2, 3, 5, 8)
LUCAS = (2, 1, 3, 4, 7, 11)


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'fibonacci', choices=choices)
    root = 60+rng.randrange(3)
    for s, (start, end, sec) in enumerate(sections):
        world = (0, 2, 4, 5, 7, 9, 11) if s % 2 == 0 else tuple(range(12))
        rhythm = FIBONACCI if s % 2 == 0 else LUCAS
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, 'Diatonic / Fibonacci' if s % 2 == 0 else 'Chromatic / Lucas')
            at, j = start, 0
            while at < end:
                length = rhythm[(j+i) % 6]*.5
                pitch = root+world[(j+i*2) % len(world)]
                put(part, at, min(length, end-at), fit(pitch, name, sec))
                at += length
                j += 1
    return finish(score, total)
