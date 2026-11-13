"""Psychological realism: Tolstoy's dialectic of the soul, Flaubert, Chekhov's longer prose."""
from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('Prose in the scenes the frame gives, over the time span it names. The inner life is narrated: '
         'free indirect discourse, the hero\'s thought sliding into the narrator\'s voice; every act has a '
         'cause in feeling that the text follows step by step, including the self-deceptions. Time passes '
         'and the hero changes by the end. Paragraphs of ordinary length, scenes separated by blank lines. '
         'The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'psychological_realism', 'title': 'study', 'seed': 1, 'scenes': 4}
SPANS = ['one day', 'one season', 'one year', 'a decade']
RANGES = [(900, 1800), (1200, 2400), (1800, 3200)]


def skeleton(plan, rng):
    scenes = plan.get('scenes', 4)
    low, high = rng.choice(RANGES)
    return {'scenes': scenes, 'span': rng.choice(SPANS), 'min_words': low, 'max_words': high,
            'min_paragraphs': scenes * 2}


def check(text, frame, language):
    return length_problems(text, frame) + paragraph_problems(text, frame['min_paragraphs'])
