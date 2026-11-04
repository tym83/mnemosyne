"""Diatonic M walks paired with nearest alternating upper/lower tonic T tones."""
from music21 import articulations
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, put, finish


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score,rng,sections,total = setup(plan,seed,'tintinnabuli', choices=choices)
    tonic = int(plan.get('tonic',60)) % 12
    scale = {(tonic+x)%12 for x in (0,2,3,5,7,8,10)}
    triad = {(tonic+x)%12 for x in (0,3,7)}
    for start,end,sec in sections:
        step = 0
        at = start
        while at < end:
            length = min(4 if sec['density'] < .6 else 2,end-at)
            for i,(part,name) in enumerate(zip(score.parts,ENSEMBLES[plan['ensemble']])):
                low,high = limits(name,sec)
                pool = [p for p in range(low,high+1) if p%12 in scale]
                target_centre = (low+high)/2 - (12 if plan['ensemble']=='piano' and i==1 else 0)
                centre = min(range(len(pool)),key=lambda j:abs(pool[j]-target_centre))
                m = pool[max(0,min(len(pool)-1,centre+step))]
                if i%2:
                    candidates = [p for p in range(low,high+1) if p%12 in triad]
                    side = [p for p in candidates if (p <= m if int(at-start)//2%2 else p >= m)]
                    pitch = min(side or candidates,key=lambda p:abs(p-m))
                else:
                    pitch = m
                # Shared breathing, then a bell-like T attack against the M line.
                sounding = length * .75 if length >= 1 else length
                put(part,at,sounding,pitch,articulations.Tenuto())
            step = max(-3,min(3,step+rng.choice([-1,1])))
            at += length
    return finish(score,total)


# Authorized performance freedom; the note grammar above remains invariant.
FREE_CHANNELS = {'dynamics': 'M/T pitch rules remain fixed; touch within each written dynamic is free.', 'period_quarters': 0.5, 'levels': 16, 'step_percent': 0.25, 'max_deviation_percent': 1.875}
