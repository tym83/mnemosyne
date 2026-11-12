"""Sonnet: fourteen lines, Petrarchan or Shakespearean, a volta; or a crown of sonnets."""
from ..form import lines, scheme, stanzas

KIND = 'poetry'
RULES = ('Fourteen lines. Petrarchan: octave ABBAABBA and sestet CDECDE, the turn (volta) at line 9. '
         'Shakespearean: ABAB CDCD EFEF GG, the turn in the couplet. The frame names the type. '
         'In a crown, the last line of each sonnet opens the next.')
EXAMPLE_PLAN = {'school': 'sonnet', 'title': 'study', 'seed': 1, 'count': 1}
TYPES = {'petrarchan': 'ABBAABBACDECDE', 'shakespearean': 'ABABCDCDEFEFGG'}


def skeleton(plan, rng):
    return {'type': rng.choice(sorted(TYPES)), 'count': plan.get('count', 1)}


def check(text, frame, language):
    problems = []
    sonnets = [lines(s) for s in stanzas(text)] if frame['count'] > 1 else [lines(text)]
    if frame['count'] > 1 and len(sonnets) != frame['count']:
        problems.append(f'{frame["count"]} sonnets expected, found {len(sonnets)}')
    for i, ls in enumerate(sonnets):
        if len(ls) != 14:
            problems.append(f'sonnet {i+1}: fourteen lines expected, found {len(ls)}')
            continue
        if language in ('ru', 'sr', 'pl', 'en', 'es', 'it', 'pt', 'de', 'fr'):
            scheme(ls, TYPES[frame['type']], problems)
        if i and ls[0] != sonnets[i-1][-1]:
            problems.append(f'sonnet {i+1} must open with the last line of sonnet {i}')
    return problems
