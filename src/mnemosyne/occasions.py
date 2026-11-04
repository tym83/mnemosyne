"""Private scheduler: occasions cross only as genre and scheduled moment.

Publication uses fixed delayed batches for circle/world. This mitigates timing
correlation; it is not a claim of anonymity against an observer of all works.
"""
import math

GENRES = {'tenant_birth': 'portrait', 'tenant_deletion': 'requiem', 'upgrade': 'new_era'}
LEVELS = ('workshop', 'circle', 'world')


def occasion(kind, night, publicity='world'):
    if publicity not in LEVELS:
        raise ValueError('unknown publicity level')
    return dict(genre=GENRES[kind], moment=night, publicity=publicity)


def release_night(moment, publicity):
    if publicity not in LEVELS:
        raise ValueError('unknown publicity level')
    return moment if publicity == 'workshop' else (math.floor(moment/30)+2)*30


def programme(work, publicity='world'):
    """Separate outward catalogue: never serialize a private work wholesale."""
    if publicity not in LEVELS:
        raise ValueError('unknown publicity level')
    result = {'genre': work.get('kind', 'study')}
    if publicity == 'workshop':
        result.update(work=work['id'], moment=work['night'])
    elif publicity == 'circle':
        result['artist'] = work['id'].rsplit('-w', 1)[0]
    else:
        result['artist'] = 'The Chronicler'
    return result


def synthetic(facts, start, end, night, publicity='world'):
    """Scheduler-side adapter. Names, causes and versions are discarded here."""
    from datetime import datetime
    result = []
    for tenant in facts['tenants']:
        for key, kind in [('born', 'tenant_birth'), ('died', 'tenant_deletion')]:
            if tenant.get(key) and start <= datetime.fromisoformat(tenant[key]) < end:
                result.append(occasion(kind, night, publicity))
    if start <= datetime.fromisoformat(facts['upgrade']['at_utc']) < end:
        result.append(occasion('upgrade', night, publicity))
    return result


def live(reading, night, publicity='world'):
    return [occasion(kind, night, publicity) for kind in reading['events'] if kind in GENRES]
