"""Bylina: a sung epic in long unrhymed lines with three stresses, an opening, typical scenes, formulae."""
from ..form import lines

KIND = 'poetry'
RULES = ('Long unrhymed lines with three main stresses and a dactylic ending. An opening (zapev) away '
         'from the story, then the typical scenes the frame lists in order, retold with fixed formulae '
         '(epithets, repeated passages for repeated actions), and a closing (iskhod) that hands the song on. '
         'Use the formula words the frame gives at least once each.')
SCENES = ['feast', 'boast', 'saddling the horse', 'the road', 'the choice at the crossroads',
          'meeting the foe', 'the fight', 'the return', 'the reckoning']
FORMULAE = ['the clear field', 'the green wine', 'the white hands', 'the damp mother earth', 'the swift feet',
            'the bright day', 'the dark night', 'the wide road']
EXAMPLE_PLAN = {'school': 'bylina', 'title': 'study', 'seed': 1, 'scenes': 5}


def skeleton(plan, rng):
    count = plan.get('scenes', 5)
    chosen = sorted(rng.sample(range(len(SCENES)), count))
    return {'scenes': [SCENES[i] for i in chosen], 'formulae': rng.sample(FORMULAE, 3), 'min_lines': 12 * count}


def check(text, frame, language):
    problems = []
    if len(lines(text)) < frame['min_lines']:
        problems.append(f'at least {frame["min_lines"]} lines expected')
    return problems
