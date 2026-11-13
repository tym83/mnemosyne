"""One world, many inner weathers: the climate is taken differently, and a creator's own life is theirs."""
import unittest
from datetime import datetime

from mnemosyne.climate import feel, temperament
from mnemosyne.lineage import Lineage
from mnemosyne.psyche import STANCES, inner, stance


class PsycheTests(unittest.TestCase):
    def setUp(self):
        self.life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        for _ in range(60):
            self.life.step({'qualities': {'abundance': .9, 'steadiness': .9, 'renewal': .6}})

    def test_the_same_world_is_taken_in_different_ways(self):
        seen = set()
        for a in self.life.artists:
            sensed = feel(self.life.climate, a.sensitivity or temperament(a.id))
            seen |= {stance(a, sensed, n) for n in range(40)}
        self.assertGreaterEqual(len(seen), 3)
        self.assertTrue(seen <= set(STANCES))

    def test_pain_in_a_bright_world_wants_out(self):
        a = self.life.working()[0]
        a.grief, a.despair, a.openness = .9, .7, .1
        sensed = feel(self.life.climate, a.sensitivity or temperament(a.id))
        stances = [stance(a, sensed, n) for n in range(200)]
        self.assertGreater(stances.count('contrast'), stances.count('resonance'))

    def test_own_life_is_told_and_the_cluster_is_not(self):
        a = self.life.working()[0]
        a.despair, a.isolation = .6, .8
        text = inner(self.life, a)
        self.assertIn('отчаяние', text)
        self.assertIn('одинок', text)
        self.assertNotIn('leonia', text)


class OriginsTests(unittest.TestCase):
    def test_every_creator_carries_their_own_life_before_art(self):
        from types import SimpleNamespace
        from mnemosyne.psyche import origins
        lives = {origins(SimpleNamespace(id=f'c{i}')) for i in range(12)}
        self.assertEqual(len(lives), 12)
        self.assertEqual(origins(SimpleNamespace(id='c1')), origins(SimpleNamespace(id='c1')))


if __name__ == '__main__':
    unittest.main()
