"""Skaz (Leskov, Zoshchenko): the tale of a narrator with his own speech, told to a listener."""
from ._prose import SENTENCE_END, length_problems

KIND = 'prose'
RULES = ('A tale told aloud by a narrator who is not the author: the frame names who he is. His speech '
         'is the form: his own words, malapropisms and favourite turns, digressions, addresses to the '
         'listener (questions and exclamations), his sure view of things that the reader sees differently. '
         'First person, as if spoken, without literary polish. The frame sets the word range and the number '
         'of direct addresses to the listener.')
EXAMPLE_PLAN = {'school': 'skaz', 'title': 'study', 'seed': 1}
NARRATORS = ['a retired sergeant', 'a market woman', 'a ferryman', 'a junior clerk', 'a cab driver',
             'a sacristan', 'a barber', 'a house porter']
RANGES = [(500, 1100), (800, 1600)]


def skeleton(plan, rng):
    low, high = rng.choice(RANGES)
    return {'narrator': rng.choice(NARRATORS), 'listener': rng.choice(['a stranger on the road', 'a neighbour',
            'a fellow passenger', 'a visitor']), 'min_words': low, 'max_words': high, 'addresses': 2}


def check(text, frame, language):
    problems = length_problems(text, frame)
    count = len([m for m in SENTENCE_END.findall(text) if any(c in m for c in '?!？！')])
    if count < frame['addresses']:
        problems.append(f'at least {frame["addresses"]} questions or exclamations to the listener expected')
    return problems
