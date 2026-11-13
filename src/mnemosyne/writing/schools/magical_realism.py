"""Magical realism after Marquez: a family across generations, the miracle told as an everyday fact."""
from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('A family chronicle across the number of generations the frame gives. The first sentence looks '
         'forward from a future moment to a past one (\'Many years later, facing ..., he was to remember ...\'). '
         'Names return through generations and bring their temper with them. Time circles. Exaggeration is '
         'exact, with a precise number; the miracle is told in the flat voice of a record, with no surprise '
         'and no explanation. One generation per block, blocks separated by blank lines. The frame sets the '
         'word range.')
EXAMPLE_PLAN = {'school': 'magical_realism', 'title': 'study', 'seed': 1, 'generations': 3}
RANGES = [(900, 1800), (1400, 2600)]


def skeleton(plan, rng):
    generations = plan.get('generations', 3)
    low, high = rng.choice(RANGES)
    return {'generations': generations, 'miracles': rng.randint(1, 3), 'min_words': low, 'max_words': high,
            'min_paragraphs': generations * 2}


def check(text, frame, language):
    return length_problems(text, frame) + paragraph_problems(text, frame['min_paragraphs'])
