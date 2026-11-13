"""Nouveau roman (Robbe-Grillet, Sarraute, Simon): objects and surfaces, the same scene repeated and shifted."""
from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('A text of objects and surfaces: exact geometric description of the things the frame names, with '
         'no psychology, no explained motive, no symbols. One scene is described again and again, each '
         'time slightly shifted (a detail changes, the order changes, the viewpoint moves), so that the '
         'reader cannot fix what happened. Present tense, a neutral eye. One description per block, blocks '
         'separated by blank lines. The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'nouveau_roman', 'title': 'study', 'seed': 1, 'passes': 4}
OBJECTS = ['a staircase', 'a window with a blind', 'a glass on a table', 'a flight of tiles', 'a lamp',
           'a banister', 'a coffee cup', 'a door left ajar', 'a stain on a wall', 'a razor']
RANGES = [(500, 1100), (800, 1500)]


def skeleton(plan, rng):
    passes = plan.get('passes', 4)
    low, high = rng.choice(RANGES)
    return {'passes': passes, 'objects': rng.sample(OBJECTS, 3), 'min_words': low, 'max_words': high}


def check(text, frame, language):
    return length_problems(text, frame) + paragraph_problems(text, frame['passes'], 'descriptions')
