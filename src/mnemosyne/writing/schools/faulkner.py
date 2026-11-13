"""Faulkner: one event told by several voices, each chapter headed by the speaker's name."""
from ._prose import headings, length_problems
from ..founding import words

KIND = 'prose'
RULES = ('One event told by the number of speakers the frame gives, each in a chapter headed by the '
         'speaker\'s name alone on its line. Each voice has its own diction, its own memory, its own '
         'blindness; the voices disagree, and the event is never told whole by one of them. The past '
         'presses on the present; long sentences are allowed. Chapters are separated by blank lines. '
         'The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'faulkner', 'title': 'study', 'seed': 1, 'speakers': 4}
RANGES = [(900, 1800), (1400, 2600)]


def skeleton(plan, rng):
    speakers = plan.get('speakers', 4)
    low, high = rng.choice(RANGES)
    return {'speakers': speakers, 'min_words': low, 'max_words': high, 'min_chapter_words': 60}


def check(text, frame, language):
    problems = length_problems(text, frame)
    heads = headings(text)
    if len(set(heads)) < frame['speakers']:
        problems.append(f'{frame["speakers"]} chapters headed by distinct speaker names expected, '
                        f'found {len(set(heads))}')
        return problems
    if words(text) - sum(words(h) for h in heads) < frame['min_chapter_words'] * frame['speakers']:
        problems.append(f'each chapter needs at least {frame["min_chapter_words"]} words')
    return problems
