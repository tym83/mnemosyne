"""Close chromatic canons, independent speeds and continuous slow registral drift."""
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score,rng,sections,total = setup(plan,seed,'micropolyphony', choices=choices)
    motif = [0]
    for _ in range(23):
        motif.append(max(-2,min(2,motif[-1]+rng.choice([-1,1]))))
    names = ENSEMBLES[plan['ensemble']]
    for start,end,sec in sections:
        bounds = [limits(name,sec) for name in names]
        common_low,common_high = max(a for a,b in bounds),min(b for a,b in bounds)
        centre = (common_low+common_high)/2
        for i,part in enumerate(score.parts):
            low,high = bounds[i]
            speed = (.5,.75,1,1.25)[i%4] * (2 if sec['density'] < .5 else 1)
            at = start+i*.25
            j = 0
            while at < end:
                drift = round(4*float((at-start)/(end-start))-2)
                pitch = max(low,min(high,round(centre)+motif[j%len(motif)]+drift+(i%3)-1))
                put(part,at,min(speed,end-at),pitch)
                at += speed
                j += 1
    return finish(score,total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'Canonic strands and pitch bands remain fixed; independent strand intensity is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
