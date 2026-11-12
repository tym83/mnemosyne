"""Eluard: an anaphora that returns at every stanza, plain words in impossible pairs, a final naming."""
from ..form import lines, stanzas

KIND = 'poetry'
RULES = ('Short transparent lines. Every stanza opens its lines with the same anaphora (the frame gives '
         'its shape, the writer finds the words in their language). Plain words in impossible pairs, no '
         'heavy metaphor. The last stanza names, at last, what the anaphora was addressing.')
EXAMPLE_PLAN = {'school': 'eluard', 'title': 'study', 'seed': 1, 'stanzas': 8}


def skeleton(plan, rng):
    return {'stanzas': plan.get('stanzas', 8), 'lines': rng.choice([3, 4]),
            'anaphora': rng.choice(['On ... I write your name', 'For ...', 'In every ...', 'I saw ...'])}


def check(text, frame, language):
    problems = []
    found = stanzas(text)
    if len(found) != frame['stanzas']:
        problems.append(f'{frame["stanzas"]} stanzas expected, found {len(found)}')
    openings = []
    for st in found[:-1]:
        ls = lines(st)
        if len(ls) != frame['lines'] and len(ls) != frame['lines'] + 1:
            problems.append(f'stanzas of about {frame["lines"]} lines expected')
        words = ls[0].split()[:2] if ls else []
        openings.append(' '.join(words).lower())
    if openings and len(set(openings)) > max(1, len(openings) // 3):
        problems.append('the anaphora must return at the start of the stanzas')
    return problems
