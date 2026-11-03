"""Limited-transposition mode, palindromic rhythms, added values and bird figures."""
from .common import ENSEMBLES, setup, put, finish
from .material import fit, mark

MODE = (0, 1, 3, 4, 6, 7, 9, 10)
RHYTHM = (1, .5, 1.5, .5, 1)


def compose(plan, seed):
    score, rng, sections, total = setup(plan, seed, 'messiaen')
    transposition = rng.randrange(3)
    for s, (start, end, sec) in enumerate(sections):
        for i, (part, name) in enumerate(zip(score.parts, ENSEMBLES[plan['ensemble']])):
            mark(part, start, 'Mode II; palindrome + added value; bird arabesques')
            at, j = start, 0
            while at < end:
                bird = i == 0 and j % 13 >= 8
                length = .25 if bird else RHYTHM[j % 5] + (.25 if j % 5 == 2 else 0)
                pc = MODE[rng.randrange(8)] if bird else MODE[(j+i*2+s) % 8]
                pitch = fit(60+transposition+pc+(12 if bird else 0), name, sec)
                if name == 'piano' and not bird:
                    pitch = sorted({fit(60+transposition+MODE[(j+k) % 8], name, sec) for k in (0, 2, 5)})
                put(part, at, min(length, end-at), pitch)
                at += length
                j += 1
    return finish(score, total)
