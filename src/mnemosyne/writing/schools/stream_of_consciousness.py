"""Stream of consciousness after Woolf: one day in the inner time of a mind, long sentences, shifting focus."""
from ._prose import length_problems, longest_sentence, paragraph_problems

KIND = 'prose'
RULES = ('Prose that follows the movement of a mind through one day, not events: perception, memory and '
         'speech pass into each other without markers. Long sentences that carry the current, at least one '
         'of about thirty words or more. The frame names the moments of the day; each moment is its own '
         'block, separated by blank lines, and the focus may slide from one mind to another inside it. '
         'The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'stream_of_consciousness', 'title': 'study', 'seed': 1, 'moments': 4}
HOURS = ['dawn', 'morning', 'noon', 'afternoon', 'dusk', 'evening', 'night']
RANGES = [(700, 1500), (1000, 2200)]


def skeleton(plan, rng):
    moments = plan.get('moments', 4)
    start = rng.randint(0, len(HOURS) - moments) if moments < len(HOURS) else 0
    low, high = rng.choice(RANGES)
    return {'moments': HOURS[start:start + moments] if moments <= len(HOURS) else HOURS,
            'min_words': low, 'max_words': high, 'min_long_sentence': 30}


def check(text, frame, language):
    problems = length_problems(text, frame) + paragraph_problems(text, len(frame['moments']), 'moments')
    if longest_sentence(text) < frame['min_long_sentence'] * .8:
        problems.append(f'a long flowing sentence of about {frame["min_long_sentence"]} words expected')
    return problems
