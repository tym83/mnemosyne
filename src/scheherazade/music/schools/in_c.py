"""Original shared modules, independent repeats, at most two modules apart."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'in_c', choices=choices)
    modules = [[rng.choice([0, 2, 5, 7, 9]) for _ in range(n)] for n in (3, 5, 2, 7, 4, 6, 3, 5)]
    for start, end, sec in sections:
        positions = [0] * len(score.parts)
        next_at = [start] * len(score.parts)
        repeats = [0] * len(score.parts)
        while min(next_at) < end:
            i = min(range(len(next_at)), key=next_at.__getitem__)
            part, name = score.parts[i], ENSEMBLES[plan['ensemble']][i]
            at, module = next_at[i], positions[i]
            mark(part, at, f'Module {module+1}; independent pulse')
            for pc in modules[module]:
                length = rng.choice([.5, .75])
                put(part, at, min(length*.5, end-at), fit(60+pc, name, sec))
                at += length
                if at >= end:
                    break
            repeats[i] += 1
            if module < len(modules)-1 and module < min(positions)+2 and (repeats[i] >= 4 or rng.random() < .4):
                positions[i] += 1
                repeats[i] = 0
            next_at[i] = at
    return finish(score, total)
