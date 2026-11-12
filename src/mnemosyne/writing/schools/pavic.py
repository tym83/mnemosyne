"""Pavic: a novel as a lexicon; entries in alphabetical order, read in any order, cross-referenced."""
import re

KIND = 'prose'
RULES = ('A lexicon novel. Entries headed by a word or name in capitals on their own line, in alphabetical '
         'order of the writer\'s language. Each entry tells part of one story that no entry tells whole. '
         'Cross-references are marked with an arrow and the headword (→ HEADWORD) and must point to entries '
         'that exist. The frame gives how many entries and how many references each needs.')
EXAMPLE_PLAN = {'school': 'pavic', 'title': 'study', 'seed': 1, 'entries': 9}


def skeleton(plan, rng):
    count = plan.get('entries', 9)
    return {'entries': count, 'references': [rng.randint(1, 3) for _ in range(count)]}


def check(text, frame, language):
    heads = re.findall(r'^([^\W\d_][^\n]{0,60})$', text, flags=re.M)
    heads = [h.strip() for h in heads if h.strip() == h.strip().upper() and len(h.strip()) > 1]
    problems = []
    if len(heads) != frame['entries']:
        problems.append(f'{frame["entries"]} entries expected, found {len(heads)}')
    if heads != sorted(heads):
        problems.append('entries must be in alphabetical order')
    refs = re.findall(r'→\s*([^\W\d_][\w\- ]*[^\W\d_])', text)
    missing = sorted({r.strip() for r in refs if r.strip().upper() not in heads})
    if missing:
        problems.append('references to missing entries: ' + ', '.join(missing))
    if len(refs) < sum(frame['references']):
        problems.append(f'at least {sum(frame["references"])} cross-references expected')
    return problems
