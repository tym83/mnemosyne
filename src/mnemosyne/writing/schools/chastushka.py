"""Chastushka: four lines of trochaic tetrameter, even lines rhyme, first person, a twist at the end."""
from ..form import lines, scheme, syllables, stanzas

KIND = 'poetry'
RULES = ('Quatrains of four short lines, about 7-9 syllables each, even lines rhyme (xAxA). '
         'First person, spoken to a crowd; the last line turns or teases. A refrain may close the set.')
EXAMPLE_PLAN = {'school': 'chastushka', 'title': 'study', 'seed': 1, 'count': 4}


def skeleton(plan, rng):
    return {'stanzas': plan.get('count', 4), 'refrain': rng.random() < .3}


def check(text, frame, language):
    problems = []
    found = stanzas(text)
    expected = frame['stanzas'] + (1 if frame['refrain'] else 0)
    if len(found) not in (frame['stanzas'], expected):
        problems.append(f'{frame["stanzas"]} quatrains expected, found {len(found)}')
    for i, st in enumerate(found[:frame['stanzas']]):
        ls = lines(st)
        if len(ls) != 4:
            problems.append(f'stanza {i+1}: four lines expected')
            continue
        counts = [syllables(l, language) for l in ls]
        if None not in counts and any(not 6 <= c <= 10 for c in counts):
            problems.append(f'stanza {i+1}: syllables {counts}, expected about 7-9')
        if language in ('ru', 'sr', 'pl', 'en', 'es', 'it', 'pt', 'de', 'fr'):
            scheme(ls, 'xAxA', problems)
    return problems
