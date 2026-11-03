"""Shared canon at sqrt(2), sqrt(3), golden-ratio speeds with integrated acceleration."""
import math
from .common import ENSEMBLES, setup, put, finish
from .material import fit, grid, mark

RATIOS = (1, math.sqrt(2), math.sqrt(3), (1+math.sqrt(5))/2)


def onset(index, ratio, span):
    # integral of rate r*(1+t/span) gives index = r*(t+t²/(2*span)).
    return span * (math.sqrt(1+2*index/(ratio*span))-1)


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'tempo_canon')
    cell = rng.sample(range(12), 9)
    for start, end, sec in sections:
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, f'Accelerating canon, ratio {RATIOS[i%4]:.8f}; 1/32-quarter grid')
            j, span = 0, float(end-start)
            while (at := start+grid(onset(j, RATIOS[i % 4], span))) < end:
                next_at = start+grid(onset(j+1, RATIOS[i % 4], span))
                put(part, at, min(next_at-at, end-at), fit(60+cell[j % 9], name, sec))
                j += 1
    return finish(score, total)
