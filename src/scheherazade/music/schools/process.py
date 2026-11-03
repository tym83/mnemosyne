"""One pattern, continuous phase displacement, then addition and substitution."""
from .common import ENSEMBLES, setup, put, finish
from .material import fit, grid, mark


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'process')
    cell = [rng.choice([60, 62, 64, 67, 69]) for _ in range(8)]
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, ('phase', 'add', 'substitute')[s % 3])
            j = 0
            step = .5 * (1 - i * .0075) if s % 3 == 0 else .5
            while (at := start + grid(j * step)) < end:
                cycle, pos = divmod(j, 8)
                active = 8 if s % 3 == 0 else min(8, 1 + cycle // 2)
                pitch = cell[pos] if pos < active else (None if s % 3 == 1 else cell[0])
                put(part, at, min(.25, end-at), None if pitch is None else fit(pitch, name, sec))
                j += 1
    return finish(score, total)
