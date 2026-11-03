"""Six seeded coin lines select independent pitch, duration, silence and dynamic."""
from .common import ENSEMBLES, setup, limits, put, finish
from .material import mark


def oracle(rng):
    return sum((sum(rng.randrange(2) for _ in range(3)) % 2) << bit for bit in range(6))


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'chance')
    for start, end, sec in sections:
        for part, name in zip(score.parts, ENSEMBLES[plan['ensemble']]):
            at = start
            low, high = limits(name, sec)
            while at < end:
                pitch = low + oracle(rng) % (high-low+1)
                length = [.5, 1, 1.5, 2, 3, 4, 6, 8][oracle(rng) % 8]
                silence = oracle(rng) < 24
                mark(part, at, 'Prepared resonance (synthesis)', ['ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff'][oracle(rng) % 8])
                put(part, at, min(length, end-at), None if silence else pitch)
                at += length
    return finish(score, total)
