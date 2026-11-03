"""One pitch centre: quarter-tone inflections, dynamic and timbral form."""
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed, *, choices: ChoiceSource | None = None):
    score, rng, sections, total = setup(plan, seed, 'scelsi', choices=choices)
    centre = plan.get('centre', 62)+rng.choice([0, 1])
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            at, j = start, 0
            while at < end:
                mark(part, at, ['dark', 'bright', 'breathy'][s % 3], ['ppp', 'p', 'mf', 'p'][(j+s+i) % 4])
                pitch = fit(centre + [0, .5, 0, -.5][(j+i) % 4], name, sec)
                put(part, at, min(4+i*.5, end-at), pitch)
                at += 4+i*.5
                j += 1
    return finish(score, total)
