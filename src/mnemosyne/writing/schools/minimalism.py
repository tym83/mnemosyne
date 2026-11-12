"""Minimalism after Chekhov: a short story in scenes, detail instead of description, an open ending."""
import re

from ..form import stanzas

KIND = 'prose'
RULES = ('A short story in the scenes the frame gives. No author\'s judgement, no explained feelings: '
         'one exact detail stands for them. Short paragraphs. The ending stays open: nothing is resolved '
         'in the last paragraph. The frame sets a word limit.')
EXAMPLE_PLAN = {'school': 'minimalism', 'title': 'study', 'seed': 1, 'scenes': 3}


def skeleton(plan, rng):
    scenes = plan.get('scenes', 3)
    return {'scenes': scenes, 'max_words': rng.choice([600, 900, 1200]), 'min_paragraphs': scenes * 2}


def check(text, frame, language):
    problems = []
    words = len(re.findall(r'\w+', text))
    if words > frame['max_words'] * 1.1:
        problems.append(f'{words} words; at most {frame["max_words"]}')
    if len(stanzas(text)) < frame['min_paragraphs']:
        problems.append(f'at least {frame["min_paragraphs"]} short paragraphs expected')
    return problems
