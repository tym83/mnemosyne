"""Polyphony: Dostoevsky as read by Bakhtin; voices of equal right, a scandal scene, dialogue as event."""
import re

from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('A scene-novel of several voices, each with its own idea and its own right: no voice is the '
         'author\'s. The centre is a scandal scene where everyone gathers and says too much. Dialogue is an '
         'event, not a report: the speakers answer, interrupt, confess, provoke. Spoken lines each on their '
         'own line, opened with a dash or a quotation mark. The frame gives the number of voices, '
         'the scenes and the word range.')
EXAMPLE_PLAN = {'school': 'polyphony', 'title': 'study', 'seed': 1, 'voices': 4}
LINE = re.compile(r'^\s*[—–\-«"“„「『]', re.M)
RANGES = [(900, 1800), (1400, 2600)]


def skeleton(plan, rng):
    voices = plan.get('voices', 4)
    low, high = rng.choice(RANGES)
    return {'voices': voices, 'scenes': rng.randint(2, 4), 'min_words': low, 'max_words': high,
            'min_spoken_lines': voices * 3}


def check(text, frame, language):
    problems = length_problems(text, frame) + paragraph_problems(text, frame['scenes'])
    spoken = len(LINE.findall(text))
    if spoken < frame['min_spoken_lines']:
        problems.append(f'at least {frame["min_spoken_lines"]} spoken lines (each opened with a dash or quote) '
                        f'expected, found {spoken}')
    return problems
