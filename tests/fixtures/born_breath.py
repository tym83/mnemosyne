"""Breath school: every part plays one long tone per breath; breaths lengthen, rests shorten."""
from .common import ENSEMBLES, setup, put, finish, limits


def compose(plan, seed, *, choices=None):
    score, rng, sections, total = setup(plan, seed, plan['school'], choices=choices)
    for part, name in zip(score.parts, ENSEMBLES[plan['ensemble']]):
        for start, end, sec in sections:
            low, high = limits(name, sec)
            at = start + rng.choice([0, 1, 2])
            breath = 3
            while at + breath <= end:
                put(part, at, breath, rng.randint(low, high))
                at += breath + max(1, 4 - breath // 2)
                breath = min(breath + rng.choice([1, 2]), 12)
    return finish(score, total)


FREE_CHANNELS = {'dynamics': 'Breath lengths fixed; amplitude inside a breath may move.', 'period_quarters': 0.5,
                 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
