"""Long, quiet asymmetric cycles; one duration or interval erodes per return."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'feldman', choices=choices)
    cell = [rng.choice([0, 1, 6, 7]) for _ in range(5)]
    for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
        for start, end, sec in sections:
            mark(part, start, 'Very soft; asymmetric returns, never accented', 'ppp')
            durations = [3, 5, 4, 7, 3]
            at, cycle = start, 0
            while at < end:
                for j, interval in enumerate(cell):
                    length = durations[j] + (.5 if j == cycle % 5 else 0)
                    pitch = fit(60 + interval + (1 if cycle % 4 == 3 and j == i % 5 else 0), name, sec)
                    put(part, at, min(length * .875, end-at), pitch)
                    at += length
                    if at >= end:
                        break
                cycle += 1
    return finish(score, total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Quiet register and long durations remain fixed; tiny intensity shades remain within the written level.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
