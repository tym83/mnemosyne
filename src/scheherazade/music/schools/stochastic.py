"""Quantized Poisson arrivals (exponential gaps), modular pitch sieves and glissandi."""
from music21 import articulations, spanner
from music21 import stream
from .common import ENSEMBLES, setup, limits, put, finish


def compose(plan: dict, seed: int) -> stream.Score:
    score,rng,sections,total = setup(plan,seed,'stochastic')
    phase = rng.randrange(12)
    for i,(part,name) in enumerate(zip(score.parts,ENSEMBLES[plan['ensemble']])):
        for start,end,sec in sections:
            low,high = limits(name,sec)
            sieve = [p for p in range(low,high+1) if (p-phase)%3==0 or (p-phase)%7==0]
            at = start
            while at < end:
                pitch = rng.choice(sieve)
                mass = sec['character'] in ('flowing','luminous') and name in ('violin','viola','cello','bass')
                length = min(1 if mass else .25,end-at)
                n = put(part,at,length,pitch,None if mass else articulations.Staccato())
                if mass and at+length < end:
                    direction = rng.choice([-7,7])
                    target = min(sieve,key=lambda p:abs(p-(pitch+direction)))
                    m = put(part,at+length,min(length,end-at-length),target)
                    part.insert(at,spanner.Glissando(n,m,lineType='solid'))
                    at += length*2
                else:
                    at += length
                # A Poisson process before grid quantization; no global RNG state.
                at += max(.25,round(rng.expovariate(.25+3*sec['density'])*4)/4)
    return finish(score,total)
