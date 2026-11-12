"""Haiku: three lines, 5-7-5 where syllables can be counted, a season word, a cut."""
from ..form import lines, syllables

KIND = 'poetry'
RULES = ('Three lines. Where the language counts syllables: 5, 7, 5 (one syllable of tolerance). '
         'One season word (kigo) from the frame. A cut (kireji): a pause or turn between two images. '
         'Present tense, no metaphor explained, no title.')
SEASONS = ['spring', 'summer', 'autumn', 'winter', 'new year']
EXAMPLE_PLAN = {'school': 'haiku', 'title': 'study', 'seed': 1, 'count': 3}


def skeleton(plan, rng):
    count = plan.get('count', 3)
    return {'poems': [{'season': rng.choice(SEASONS), 'cut_after': rng.choice([1, 2])} for _ in range(count)]}


def check(text, frame, language):
    problems = []
    poems = [p for p in text.split('\n\n') if p.strip()]
    if len(poems) != len(frame['poems']):
        problems.append(f'{len(frame["poems"])} haiku expected, found {len(poems)}')
    for i, poem in enumerate(poems):
        ls = lines(poem)
        if len(ls) != 3:
            problems.append(f'haiku {i+1}: three lines expected, found {len(ls)}')
            continue
        counts = [syllables(l, language) for l in ls]
        if None not in counts and any(abs(c - t) > 1 for c, t in zip(counts, (5, 7, 5))):
            problems.append(f'haiku {i+1}: syllables {counts}, expected 5-7-5')
    return problems
