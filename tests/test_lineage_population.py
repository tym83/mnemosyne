"""Retrospective trajectory checks, never inputs to the fate engine.

Run this CPU population experiment in a studio pod. Criteria are quantitative
proxies for synthetic works, not verdicts about artistic merit.
"""
import unittest
from collections import Counter
from datetime import datetime
from statistics import median, pstdev

from mnemosyne.lineage import Lineage, Parameters


def trajectories(life):
    found = Counter()
    for a in life.artists:
        ev = [e for e in life.events if e['artist'] == a.id]
        works = [w for w in a.catalogue if w['kind'] != 'last_piece']
        brilliant = [w for w in works if w['quality'] >= .7 and w['verdict'] == 'accept']
        silences = [e for e in ev if e['kind'] == 'silence']
        returns = [e for e in ev if e['kind'] == 'return']
        if brilliant and silences:
            s = silences[0]['night']
            end = next((e['night'] for e in returns if e['night'] > s), a.death_night or life.night)
            if s - a.birth_night < 100 and any(w['night'] < s for w in brilliant) and end - s > 200:
                found['meteor'] += 1
            if sum(w['night'] - a.birth_night < 50 for w in brilliant) >= 3 and s - a.birth_night < 100 and silences[0]['facts']['cause'] == 'exhaustion':
                found['prodigy_burnout'] += 1
        if brilliant and brilliant[0]['night'] - a.birth_night > 200 and len(brilliant) >= 3:
            found['late_bloomer'] += 1
        if a.age > 500 and len(works) > 40 and not silences and pstdev(w['quality'] for w in works) < .18:
            found['craftsman'] += 1
        if any(e['facts']['silence'] > 200 for e in returns) and any(p.get('cause') == 'return' and p['period'] == 'late' for p in a.periods):
            found['return_late'] += 1
        discoveries = [e for e in ev if e['kind'] == 'rediscovery']
        if discoveries:
            found['rediscovered'] += 1
        if a.death_night and any(e['facts']['posthumous'] for e in discoveries) and all(
                c['state']['recognition'] < .35 for c in life.biographies[a.id].chapters if c['night'] < a.death_night) and not any(
                e['kind'] == 'recognition' and e['night'] < a.death_night for e in ev):
            found['posthumous'] += 1
        if any(e['kind'] == 'school' for e in ev):
            students = [b for b in life.artists if a.id in b.teachers]
            relations = {e['relation'] for e in life.influences if e['source'] == a.id}
            if students and {'rebellion', 'apprenticeship'} <= relations:
                found['school_with_heretics'] += 1
        if any(e['source'] == a.id and e['relation'] == 'rivalry' for e in life.influences):
            found['rivals'] += 1
        if a.renounced and a.status in ('silent', 'dead'):
            found['renunciation'] += 1
        changes = [e for e in ev if e['kind'] == 'illness_recovery' and e['facts']['altered_voice']]
        if any(sum(w['night'] > e['night'] for w in works) >= 20 for e in changes):
            found['tower'] += 1
        if a.age > 200 and not any(a.id in (e['source'], e['target']) for e in life.influences):
            found['hermit'] += 1
    return found


class PopulationTests(unittest.TestCase):
    def test_many_lineages_have_many_lives(self):
        found, events, seasons, deaths = Counter(), Counter(), Counter(), []
        for seed in range(48):
            life = Lineage('population', datetime(2025, 1, 1), seed, Parameters(synthetic_schools=True))
            for n in range(365 * 5):
                # Inner life has long stretches, without any incident identity.
                weight = .8 if (n // 200 + seed) % 3 else .2
                life.step(dict(strain=weight, scars=weight, loss=weight, turbulence=weight))
                self.assertLessEqual(len(life.working()), life.p.spaces)
            found.update(trajectories(life))
            events.update(e['kind'] for e in life.events)
            seasons.update(e['facts']['season'] for e in life.events if e['kind'] == 'fertility')
            deaths.extend(a.age for a in life.artists if a.status == 'dead')
            for a in life.artists:
                if a.death_night is not None:
                    self.assertTrue(all(w['night'] <= a.death_night for w in a.catalogue))
        required = {'meteor', 'late_bloomer', 'craftsman', 'posthumous', 'prodigy_burnout',
                    'return_late', 'school_with_heretics', 'rivals', 'renunciation', 'tower', 'rediscovered', 'hermit'}
        print('trajectory counts:', dict(found), flush=True)
        print('lifespans:', len(deaths), 'median nights:', median(deaths),
              'min/max:', min(deaths), max(deaths), flush=True)
        self.assertFalse(required - found.keys(), required - found.keys())
        self.assertGreater(seasons['mirabilis'], 0)
        self.assertGreater(seasons['fallow'], 0)
        self.assertGreater(median(deaths), 650)
        self.assertLess(median(deaths), 800)
        self.assertLess(sum(age < 25 for age in deaths) / len(deaths), .03)
        for kind in ('illness_onset', 'illness_crisis', 'illness_recovery', 'master',
                     'illumination', 'dream', 'verification', 'years_of_silence'):
            self.assertGreater(events[kind], 0, kind)
