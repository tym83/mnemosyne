"""Every literature school has a poetics beyond its form, and a creator remembers their own work."""
import unittest
from datetime import datetime

from mnemosyne.lineage import Lineage
from mnemosyne.psyche import remembered
from mnemosyne.writing import poetics
from mnemosyne.writing.schools import SCHOOLS

AXES = ('worldview', 'reader', 'time', 'composition', 'narrator', 'language', 'devices',
        'forbidden', 'markers', 'reading', 'manifesto')


class PoeticsTests(unittest.TestCase):
    def test_every_school_has_a_full_poetics(self):
        for name, school in SCHOOLS.items():
            p = poetics.load(name)
            self.assertIsNotNone(p, name)
            for axis in AXES:
                self.assertTrue(p.get(axis), f'{name}: {axis}')
            self.assertGreaterEqual(len(p['manifesto']), 5, name)
            text = poetics.full(name, school.RULES)
            self.assertIn('Манифест', text)
            self.assertIn(school.RULES, text)

    def test_a_creator_remembers_their_last_work(self):
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        life.step({})
        a = life.working()[0]
        work = life.record_work(a.id, {'feature': [0, 0, 0, 0], 'quality': .7, 'verdict': 'accept',
                                       'idea': 'сад за пекарней', 'novelty': 1., 'process': {}})
        work.update(title='Сад', excerpt='Фрау Керн положила ключ на стол.', diary='оставил второй стул')
        memory = remembered(life, a)
        self.assertIn('«Сад»', memory)
        self.assertIn('Фрау Керн', memory)
        self.assertNotIn('leonia', memory)


if __name__ == '__main__':
    unittest.main()
