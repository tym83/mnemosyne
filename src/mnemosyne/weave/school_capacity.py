"""Audit existing grammar limits; historical raw grammar, excluding approved free surfaces.

Run with python -m mnemosyne.weave.school_capacity. Exhaustively measures
the MusicXML support for single-choice schools; bounds others where possible.
"""
import argparse
import json
import math
from pathlib import Path
import tempfile

from music21 import converter

from mnemosyne.music.render import note_events
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.music.schools.common import ENSEMBLES
from .payload import OVERHEAD

PLANS = Path(__file__).parents[1] / 'music/schools/plans'
SINGLE = {'drone': 2, 'scelsi': 2, 'spectral': 3, 'fibonacci': 3,
          'ustvolskaya': 3, 'polystylism': 3}


class SingleChoice:
    """Enumerate the only random decision; fail if a grammar adds more."""
    def __init__(self, index):
        self.index = index
        self.calls = 0

    def choice(self, options):
        self.calls += 1
        if self.calls != 1:
            raise ValueError('school no longer has just one choice')
        return options[self.index]

    def randrange(self, stop):
        return self.choice(range(stop))


def support(name, plan):
    """Count distinguishable sounding-event scores after actual XML export."""
    observed = set()
    with tempfile.TemporaryDirectory() as tmp:
        for index in range(SINGLE[name]):
            source = SingleChoice(index)
            score = SCHOOLS[name].compose(plan, plan['seed'], choices=source)
            if source.calls != 1:
                raise ValueError('expected one random decision')
            path = Path(tmp) / f'{index}.musicxml'
            score.write('musicxml', fp=path)
            parsed = converter.parse(path).toSoundingPitch().stripTies()
            observed.add(repr(note_events(parsed)))
    return len(observed)


def bound(name, plan):
    """Upper bounds on information before any losses in notation."""
    fixed = {'additive': math.log2(math.factorial(5)),
             'feldman': 10, 'process': 8*math.log2(5),
             'micropolyphony': 23, 'serial': math.log2(math.factorial(12)),
             'tempo_canon': math.log2(math.factorial(12)//math.factorial(3))}
    if name == 'aleatoric_counterpoint':
        return len(plan['form'])*len(ENSEMBLES[plan['ensemble']])*math.log2(12*11*10*9)
    return fixed.get(name)


def report():
    lines = ['# School capacity audit', '',
             'Historical raw-grammar support only; see school_audit for the implemented surface codec.',
             'Measured rows enumerate every possible score for the supplied plan,',
             'export MusicXML and count distinct recovered sounding-event sequences.',
             'Other numeric rows are source-alphabet upper bounds, NOT measured capacity.',
             'Bits/minute uses written duration, without audio tails.', '',
             '| School | Bits/work | Bits/minute | Evidence |',
             '| --- | ---: | ---: | --- |']
    for name in sorted(SCHOOLS):
        plan = json.loads((PLANS / f'{name}.json').read_text())
        if name in SINGLE:
            count = support(name, plan)
            bits = math.log2(count)
            evidence = f'Measured XML support: {count} scores; zero whole bytes'
        else:
            bits = bound(name, plan)
            evidence = 'Upper bound; inversion unimplemented' if bits is not None else 'Unmeasured; inversion unimplemented'
        values = ('—', '—') if bits is None else (f'{bits:.6f}', f'{bits*60/plan["duration"]:.6f}')
        lines.append(f'| {name} | {values[0]} | {values[1]} | {evidence} |')
    lines += ['', '## Historical constraints of the raw grammar', '',
              f'The existing payload envelope has {OVERHEAD} bytes ({OVERHEAD*8} bits) of overhead,',
              'before compressed data. Even an alternative authenticated codec cannot encode',
              'an arbitrary byte in a grammar with only two or three possible scores.',
              'Repeating a cell or lengthening these pieces does not add independent choices.', '',
              'Raw RNG choices are not an invertible alphabet: chance reduces coin triples',
              'to parity, reduces oracle values modulo pitch/duration counts and hides pitches',
              'during rests; tintinnabuli discards its final step in every section;',
              'stochastic rounds continuous gaps and discards the last gap. An arithmetic',
              'decoder must operate on observable equivalence classes with their aggregate',
              'probabilities, rather than recover these discarded random draws.', '',
              'The author approved additional surface choices and series transport. The old',
              'raw grammar remains unchanged; see weave.schools and school_audit.',
              'Woven/unwoven histograms and tamper tests are implemented in school_audit; there',
              'was no feasible all-school channel under the original raw-grammar constraints.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('out/works/music/schools/CAPACITY.md'))
    args = parser.parse_args()
    # Keep earlier audit artifacts, just as generated works are preserved.
    if args.output.exists():
        raise FileExistsError(args.output)
    result = report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out:
        out.write(result)
    print(result)


if __name__ == '__main__':
    main()
