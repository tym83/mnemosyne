import unittest
from datetime import datetime

from mnemosyne.lineage import Lineage


class DespairTest(unittest.TestCase):
    def test_rejections_wound_and_acceptance_heals(self):
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        for _ in range(3):
            life.set_aside_idea(a.id, 'idea', 'too literal')
        wounded = a.despair
        self.assertGreater(wounded, 0)
        life.record_work(a.id, dict(feature=[.5] * len(a.style), novelty=.9, quality=.8, verdict='accept'))
        self.assertLess(a.despair, wounded)

    def test_deep_despair_sometimes_ends_a_life_or_a_vocation(self):
        outcomes = {'death': 0, 'renounced': 0}
        mood = {}
        for seed in range(40):
            life = Lineage('test', datetime(2025, 1, 1), seed=seed)
            a = life.artists[0]
            a.despair, a.resilience = 1., 0.
            for _ in range(200):
                a.despair = 1.
                life.step(mood)
                if a.status == 'dead' and a.death_night is not None:
                    cause = next(e['facts']['cause'] for e in life.events if e['kind'] == 'death' and e['artist'] == a.id)
                    if cause == 'despair':
                        outcomes['death'] += 1
                    break
                if a.renounced and a.status == 'silent':
                    outcomes['renounced'] += 1
                    break
        self.assertGreater(outcomes['death'], 0)
        self.assertGreater(outcomes['renounced'], 0)

    def test_heavy_times_bring_more_despair_but_it_stays_a_minority(self):
        def exits(mood):
            despair = total = 0
            for seed in range(12):
                life = Lineage('leonia', datetime(2025, 1, 1), seed=seed)
                for _ in range(730):
                    life.step(mood)
                for e in life.events:
                    if e['kind'] in ('death', 'silence'):
                        total += 1
                        despair += e['facts']['cause'] == 'despair'
            return despair, total
        calm, calm_total = exits({})
        heavy, heavy_total = exits({'qualities': {'loss': .7, 'strain': .7, 'turbulence': .6}})
        self.assertGreater(heavy / heavy_total, calm / calm_total)
        self.assertLess(heavy / heavy_total, .5)

if __name__ == '__main__':
    unittest.main()
