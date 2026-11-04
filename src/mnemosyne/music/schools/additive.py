"""Cells grow then contract, over harmony that changes only after whole cycles."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'additive', choices=choices)
    cell = rng.sample([0, 2, 4, 7, 9], 5)
    for s, (start, end, sec) in enumerate(sections):
        at, cycle = start, 0
        while at < end:
            size = [2, 3, 4, 5, 4, 3][cycle % 6]
            root = [60, 57, 65, 62][(cycle // 6 + s) % 4]
            for j in range(size):
                for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
                    pitch = root + (cell[j] if i % 2 == 0 else [0, 7][j % 2])
                    put(part, at, min(.5, end-at), fit(pitch, name, sec))
                at += .5
                if at >= end:
                    break
            cycle += 1
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Cell addition and pulse order stay fixed; local touch may breathe.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
