"""Gothic: a house, a secret, a past that returns; dread built by stages."""
from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('A tale of dread in the setting the frame names. Built by stages, each its own block separated by '
         'blank lines: arrival, an omen, the discovery of the secret, the return of the past, and a '
         'last turn that leaves the dread alive. Weather and architecture share the mood; the narrator '
         'trusts what he sees until he cannot. The terror comes from what is implied. The frame sets the '
         'number of stages and the word range.')
EXAMPLE_PLAN = {'school': 'gothic', 'title': 'study', 'seed': 1, 'stages': 5}
SETTINGS = ['an old manor on a moor', 'a monastery in the mountains', 'a house sinking into a marsh',
            'a family vault under a church', 'a sanatorium in winter', 'a lighthouse']
RANGES = [(700, 1500), (1100, 2100)]


def skeleton(plan, rng):
    stages = plan.get('stages', 5)
    low, high = rng.choice(RANGES)
    return {'setting': rng.choice(SETTINGS), 'stages': stages, 'min_words': low, 'max_words': high,
            'min_paragraphs': stages * 2}


def check(text, frame, language):
    return length_problems(text, frame) + paragraph_problems(text, frame['stages'], 'stages')
