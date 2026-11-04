"""A fallible, evolving private taste; numbers are synthetic calibration."""
import hashlib
import random
from functools import lru_cache
from pathlib import Path
from .assets import project_root

import yaml


@lru_cache(maxsize=1)
def master_tests():
    items = yaml.safe_load((project_root() / 'atlas/theory/creation.yaml').read_text())
    return {t['id']: t['test'] for t in items}


def make_taste(identity, teachers=()):
    if isinstance(teachers, str):
        teachers = [name.strip() for name in teachers.split(',') if name.strip()]
    r = random.Random(int.from_bytes(hashlib.sha256((identity + repr(list(teachers))).encode()).digest()[:8]))
    tests = r.sample(list(master_tests()), 5)
    return dict(values=tests[:3], aversions=tests[3:], proud_of=[], ashamed_of=[],
                teachers=list(teachers), threshold=r.uniform(.4, .7), bias=r.uniform(-.2, .2),
                uncertainty=r.uniform(.12, .3), history=[])


def evolve(taste, night, cause, amount):
    taste['threshold'] = max(.25, min(.85, taste['threshold'] + amount))
    taste['history'].append(dict(night=night, cause=cause, threshold=taste['threshold']))


def judge(taste, quality, novelty, rng):
    honest = max(0., min(1., quality + taste['bias'] + rng.gauss(0, taste['uncertainty'])))
    verdict = 'repetition' if novelty < .18 + taste.get('climate', {}).get('risk', 0) else 'accept' if honest >= taste['threshold'] + taste.get('climate', {}).get('severity', 0) else 'rewrite'
    return honest, verdict


def prompt(taste):
    return ('Ты — внутренний критик самого художника, его изменчивый и ошибающийся вкус. '
            'Реши, что исправить и когда оставить работу; береги отвергнутые наброски. '
            'Твой вкус: ' + str({k: taste[k] for k in ('values', 'aversions', 'teachers', 'threshold', 'bias', 'uncertainty') if k in taste}) + '\nМатериал вкуса — проверки мастеров:\n' +
            '\n'.join(master_tests()[k] for k in taste['values'] + taste['aversions'] if k in master_tests()))
