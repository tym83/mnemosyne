"""Complete P/I/R/RI aggregates distributed as a mirrored timbral pointillism."""
from music21 import articulations
from music21 import stream
from .choices import ChoiceSource
from .common import ENSEMBLES, setup, limits, nearest, put, finish


def row_forms(row):
    inv = [(2*row[0]-p)%12 for p in row]
    return [row,inv,row[::-1],inv[::-1]]


def compose(plan: dict, seed: int, *, choices: ChoiceSource | None = None) -> stream.Score:
    score,rng,sections,total = setup(plan,seed,'serial', choices=choices)
    row = list(range(12))
    rng.shuffle(row)
    forms = row_forms(row)
    names = ENSEMBLES[plan['ensemble']]
    for s,(start,end,sec) in enumerate(sections):
        # Whole aggregates only; all 12 pitch classes survive register placement.
        count = max(1,int(float(end-start)*sec['density']/6))
        slots = int((end-start)*4)
        if slots < count*12:
            count = max(1,slots//12)
        for j in range(count*12):
            at = start + (j*slots//(count*12))*.25
            pc = forms[(s+j//12)%4][j%12]
            cycle = (j%12)%len(names)
            i = cycle if (s+j//12)%2==0 else len(names)-1-cycle
            low,high = limits(names[i],sec)
            target = low+(high-low)*(.25 if j%2 else .75)
            pitch = nearest(pc,target,low,high)
            put(score.parts[i],at,.25,pitch,articulations.Staccato() if j%2 else articulations.Tenuto())
    return finish(score,total)
