"""Exact just partials enter slowly; score rounds to quarter tones, audio retains cents."""
import math
from music21 import dynamics
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'drone')
    fundamental = plan.get('fundamental', 36)+rng.choice([0, 2])
    for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
        partial = len(score.parts)-i
        at = (partial-1)*8
        # musicxml2ly carries dynamics across multi-measure rests to the first
        # note. Keep only the effective entry dynamic, avoiding conflicting marks.
        preceding = [d for d in part.getElementsByClass(dynamics.Dynamic) if d.offset <= at]
        entry_dynamic = preceding[-1].value
        for dynamic in preceding:
            part.remove(dynamic)
        part.insert(at, dynamics.Dynamic(entry_dynamic))
        exact = fundamental+12*math.log2(partial)
        for start, end, sec in sections:
            begin = max(start, at)
            if begin >= end:
                continue
            pitch = fit(exact, name, sec)
            rounded = round(pitch*2)/2
            mark(part, begin, f'Partial {partial}; {100*(pitch-rounded):+.2f} cents from written pitch')
            n = put(part, begin, end-begin, rounded)
            n.editorial.just_pitch = pitch
    return finish(score, total)
