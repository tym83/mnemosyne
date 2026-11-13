"""Epistolary: a story told in letters; what is unsaid and what is mis-sent make the plot."""
import re

from ._prose import length_problems

KIND = 'prose'
RULES = ('A story told only in letters, the number the frame gives. Each letter has a dateline or place, '
         'a salutation and a signature, and is separated from the next by a line of three asterisks (***). '
         'The writers hold different information and misread each other; one letter in the frame is lost '
         'or unanswered. The plot moves between the letters, not inside them. The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'epistolary', 'title': 'study', 'seed': 1, 'letters': 5}
SEPARATOR = re.compile(r'^\s*(?:(?:\*\s*){3,}|-{3,}|_{3,})\s*$', re.M)
RANGES = [(500, 1200), (800, 1800)]


def skeleton(plan, rng):
    letters = plan.get('letters', 5)
    low, high = rng.choice(RANGES)
    return {'letters': letters, 'correspondents': rng.randint(2, 3), 'lost_letter': rng.randint(2, letters),
            'min_words': low, 'max_words': high}


def check(text, frame, language):
    found = len([p for p in SEPARATOR.split(text) if p.strip()])
    problems = length_problems(text, frame)
    if not frame['letters'] <= found <= frame['letters'] + 2:
        problems.append(f'{frame["letters"]} letters separated by *** expected, found {found}')
    return problems
