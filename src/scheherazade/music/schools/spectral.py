"""Orchestrated partials morph from harmonic to stretched spectra, in quarter tones."""
import math
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def partial_pitch(fundamental, partial, stretch):
    return round((fundamental + 12 * math.log2(partial ** stretch))*2)/2


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'spectral')
    fundamental = plan.get('fundamental', 36) + rng.choice([0, 2, 5])
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, 'Partial spectrum; quarter-tone approximation')
            at = start
            while at < end:
                mix = float((at-start)/(end-start))
                stretch = 1 + .18 * (mix if s % 2 == 0 else 1-mix)
                pitch = partial_pitch(fundamental, i+2, stretch)
                put(part, at, min(8, end-at), fit(pitch, name, sec))
                at += 8
    return finish(score, total)
