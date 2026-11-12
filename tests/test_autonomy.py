"""The atelier's creative freedom: nothing outside it chooses ideas, schools or moods."""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from mnemosyne.lineage import Lineage
from mnemosyne.sensor import NotFound, Sensor


class ChamberTests(unittest.TestCase):
    def test_chamber_composes_every_work_of_the_night_by_itself(self):
        from mnemosyne.operator.worker import chamber
        from mnemosyne.music.schools import SCHOOLS
        life = Lineage('test', datetime(2025, 1, 1), seed=3)
        while not any(w['night'] == life.night for a in life.artists for w in a.catalogue):
            life.step({})
        tonight = [w for a in life.artists for w in a.catalogue if w['night'] == life.night]
        with tempfile.TemporaryDirectory() as tmp:
            sources, records = chamber(life, Path(tmp))
            self.assertEqual([s[0] for s in sources], [w['id'] for w in tonight])
            self.assertTrue(all(s[2] in SCHOOLS and s[1].exists() for s in sources))
            self.assertTrue(all(w['school'] in SCHOOLS for w in tonight))
            opus = [r for r in records if r['kind'] == 'Opus']
            self.assertEqual({o['spec']['artisticVerdict'] for o in opus} - {'accept', 'rewrite', 'repetition'}, set())

    def test_school_choice_is_the_artists_and_reproducible(self):
        from mnemosyne.operator.worker import choose_school
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        work = {'id': 'test-0001-w00007'}
        names = ['serial', 'drone', 'feldman']
        self.assertEqual(choose_school(a, work, names), choose_school(a, work, names))
        a.school = 'drone'
        picks = [choose_school(a, {'id': f'w{i}'}, names) for i in range(200)]
        self.assertGreater(picks.count('drone'), 120)
        self.assertGreater(len(set(picks)), 1)


class InClusterSensorTests(unittest.TestCase):
    def test_reads_through_fetch_and_keeps_forbidden_unknown(self):
        seen = []
        def fetch(path):
            seen.append(path)
            if path.endswith('/pods'):
                return {'items': []}
            if path == '/api/v1/namespaces/atelier':
                return {'metadata': {'uid': 'u', 'creationTimestamp': '2025-01-01T00:00:00Z'}}
            raise PermissionError('forbidden')
        reading = Sensor('atelier', fetch=fetch).read(now='2025-02-01T00:00:00+00:00')
        self.assertIn('/api/v1/namespaces/atelier/pods', seen)
        self.assertIn('/apis/apps/v1/namespaces/atelier/deployments', seen)
        self.assertTrue(reading['pods_observed'])
        self.assertIn('events', reading['missing'])
        self.assertEqual(reading['configuration']['age_days'], 31)

    def test_missing_namespace_is_absence_not_failure(self):
        def fetch(path):
            raise NotFound(path)
        self.assertTrue(Sensor('atelier', fetch=fetch).read()['namespace_absent'])

    def test_workshop_sensor_stays_restricted_without_fetch(self):
        with self.assertRaises(ValueError):
            Sensor('atelier')


if __name__ == '__main__':
    unittest.main()
