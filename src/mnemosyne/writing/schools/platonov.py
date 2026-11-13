"""Platonov: the shift of meaning; a seeker of truth wandering through a half-built world."""
from ._prose import length_problems, paragraph_problems

KIND = 'prose'
RULES = ('A wandering story of a naive seeker of truth, in the frame\'s number of encounters, one block '
         'each, separated by blank lines. The language slips: an abstract concept with a bodily verb, '
         'redundant causal links (because, since), the clerk\'s and the slogan\'s words turned into '
         'metaphysics, said in complete earnestness. Poverty, orphanhood, a building site that becomes a '
         'grave; a forgotten thing is picked up and kept. The frame sets the word range.')
EXAMPLE_PLAN = {'school': 'platonov', 'title': 'study', 'seed': 1, 'encounters': 4}
THINGS = ['a tin spoon', 'a broken lock', 'a child\'s shoe', 'a leaf from a ledger', 'a wheel without a cart',
          'a stopped watch', 'a bag of nails']
RANGES = [(600, 1300), (900, 1800)]


def skeleton(plan, rng):
    encounters = plan.get('encounters', 4)
    low, high = rng.choice(RANGES)
    return {'encounters': encounters, 'keeps': rng.choice(THINGS), 'min_words': low, 'max_words': high}


def check(text, frame, language):
    return length_problems(text, frame) + paragraph_problems(text, frame['encounters'], 'encounters')
