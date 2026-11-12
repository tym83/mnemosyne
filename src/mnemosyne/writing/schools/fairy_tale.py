"""Fairy tale after Propp: the functions in their fixed order, some omitted, tripled trials."""
import re

KIND = 'prose'
RULES = ('A wonder tale told by Propp\'s functions in their fixed order; the frame keeps some and drops '
         'others, never reorders them. Mark each function as a paragraph that starts with its number in '
         'square brackets, e.g. [8] for villainy. Trials come in threes. An opening formula and a closing '
         'formula of the storyteller.')
FUNCTIONS = ['absentation', 'interdiction', 'violation', 'reconnaissance', 'delivery', 'trickery',
             'complicity', 'villainy or lack', 'mediation', 'counteraction', 'departure',
             'first function of the donor', "hero's reaction", 'receipt of a magical agent',
             'guidance', 'struggle', 'branding', 'victory', 'liquidation of lack', 'return', 'pursuit',
             'rescue', 'unrecognised arrival', 'unfounded claims', 'difficult task', 'solution',
             'recognition', 'exposure', 'transfiguration', 'punishment', 'wedding']
CORE = {7, 10, 13, 18, 19, 30}  # villainy/lack, departure, magical agent, victory, liquidation, wedding (0-based)
EXAMPLE_PLAN = {'school': 'fairy_tale', 'title': 'study', 'seed': 1, 'keep': .6}


def skeleton(plan, rng):
    keep = plan.get('keep', .6)
    chosen = [i for i in range(len(FUNCTIONS)) if i in CORE or rng.random() < keep]
    return {'functions': [[i + 1, FUNCTIONS[i]] for i in chosen]}


def check(text, frame, language):
    found = [int(n) for n in re.findall(r'^\s*\[(\d+)\]', text, flags=re.M)]
    expected = [n for n, _ in frame['functions']]
    if found != expected:
        return [f'functions in order {expected} expected, found {found}']
    return []
