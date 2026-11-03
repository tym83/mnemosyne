"""Independent looping cells between synchronous conducted frames."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'aleatoric_counterpoint', choices=choices)
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            cell = rng.sample(range(12), 4)
            at, j = start, 0
            mark(part, start, 'Conducted' if s % 2 == 0 else 'Ad lib.: repeat independently until cue; one realization')
            step = 2 if s % 2 == 0 else [.5, .75, 1.25, 1.75][i % 4]
            if s % 2:
                at += i*.25
            while at < end:
                put(part, at, min(step*.75, end-at), fit(60+cell[j % 4], name, sec))
                at += step
                j += 1
    return finish(score, total)
