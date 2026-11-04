import copy
import json
import random
import unittest
from datetime import datetime
from types import SimpleNamespace

from mnemosyne.climate import qualities, temperament, feel, rhyme, tendencies, year_shape
from mnemosyne.lineage import Lineage
from mnemosyne.mood import mood
from mnemosyne.occasions import occasion, programme
from mnemosyne.sensor import Sensor


class ClimateTests(unittest.TestCase):
    def test_boundary_and_replay(self):
        a, b = [Lineage('test', datetime(2025, 1, 1), seed=14) for _ in range(2)]
        for _ in range(100):
            a.step({'qualities': {'loss': .7}, 'facts': 'CANARY payments crashed', 'words': 'CANARY'})
            b.step({'qualities': {'loss': .7}})
        self.assertEqual(a.state(), b.state())
        self.assertNotIn('CANARY', json.dumps(a.state()))
        c = Lineage.restore(json.loads(json.dumps(a.state())))
        for _ in range(10):
            a.step({'density': .9}); c.step({'density': .9})
        self.assertEqual(a.state(), c.state())
        class Writer:
            def __init__(self, nb): pass
            def ask(self, system, prompt, schema, step):
                assert 'CANARY' not in system+prompt
                return schema(text='Opinion')
        a.reception.write_words(Writer)
        with self.assertRaises(ValueError): qualities({'loss': float('nan')})
        with self.assertRaises(ValueError): qualities({'loss': 'payments'})

    def test_temperament_structure_and_rhyme(self):
        self.assertNotEqual(feel({'density': .6}, temperament('one')), feel({'density': .6}, temperament('two')))
        self.assertGreater(rhyme({'loss': 1}, {'loss': 1}), rhyme({'loss': 0}, {'loss': 1}))
        r = random.Random(4)
        samples = [tendencies({'density': 1}, {}, 'method', r)['polyphony'] for _ in range(300)]
        other = [tendencies({'density': 0}, {}, 'method', r)['polyphony'] for _ in range(300)]
        self.assertGreater(sum(samples), sum(other))
        self.assertGreater(len(set(samples)), 100)
        self.assertNotEqual(tendencies({'density': .5}, {'values': ['a']}, 'one', random.Random(1)),
                            tendencies({'density': .5}, {'values': ['b']}, 'two', random.Random(1)))
        shape = year_shape([{'strain': 0}]*200+[{'strain': 1}]*165)
        self.assertAlmostEqual(sum(shape['proportions']), 1)
        self.assertNotEqual(shape['proportions'][0], shape['proportions'][-1])
        self.assertEqual(len(shape['tension']), 32)

    def test_occasion_embargo(self):
        life = Lineage('test', datetime(2025, 1, 1))
        life.occasions.append(occasion('tenant_deletion', 0))
        a = life.artists[0]
        w = life._work(a, observation=dict(feature=[.5]*4, novelty=1, quality=.8, verdict='accept'))
        self.assertEqual(w['kind'], 'requiem')
        life.reception.register(a, w)
        self.assertFalse(life.reception.works[w['id']]['released'])
        with self.assertRaises(ValueError): life.reception.release(w['id'], 1, 'rediscovery', False)
        life.night = w['publish_after']
        life.reception.step(life)
        self.assertTrue(life.reception.works[w['id']]['released'])
        public = programme(w)
        self.assertNotIn('test', json.dumps(public))
        self.assertNotIn('moment', public)
        self.assertIn('moment', programme(w, 'workshop'))

    def test_sensor_scoping_and_unknown_metrics(self):
        commands = []
        def runner(command, **kwargs):
            commands.append(command)
            if '--raw' in command:
                return SimpleNamespace(returncode=1, stdout='', stderr='Forbidden')
            return SimpleNamespace(returncode=0, stdout=json.dumps({'items': []}))
        sensor = Sensor(runner=runner)
        reading = sensor.read(now='2025-01-01T00:00:00+00:00')
        self.assertIsNone(reading['load']['utilisation']['cpu'])
        self.assertNotIn('tenant_deletion', sensor.read(reading)['events'])
        self.assertTrue(all('get' in c and c[c.index('-n')+1]=='tenant-scheherazade' for c in commands))
        self.assertNotIn('secrets', str(commands).lower())
        self.assertNotIn('--all-namespaces', str(commands))
        with self.assertRaises(ValueError): Sensor('another-tenant')
        reading['inventory'] = {'CANARY': ['CANARY']}
        boundary = mood([reading])
        self.assertNotIn('CANARY', json.dumps(boundary))
        self.assertEqual(set(boundary), {'qualities', 'words'})

    def test_sensor_changes_and_explicit_deletion(self):
        current = {'uid': 'pod1', 'image': 'v1', 'namespace': True}
        def runner(command, **kwargs):
            resource = command[command.index('get')+1]
            if resource == '--raw':
                resource = command[-1]
            if resource.endswith('/namespaces/tenant-scheherazade'):
                if not current['namespace']:
                    return SimpleNamespace(returncode=1, stdout='', stderr='Error from server (NotFound)')
                data = {'metadata': {'uid': 'tenant1', 'creationTimestamp': '2025-01-01T00:00:00Z'}}
            elif 'metrics.k8s.io' in resource:
                data = {'items': [{'containers': [{'usage': {'cpu': '250m', 'memory': '64Mi'}}]}]}
            elif resource == 'pods':
                data = {'items': [{'metadata': {'uid': current['uid']}, 'spec': {'nodeName': 'ws1',
                    'containers': [{'image': current['image'], 'resources': {'requests': {'cpu': '500m', 'memory': '128Mi'}}}]},
                    'status': {'phase': 'Running', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]}
            else: data = {'items': []}
            return SimpleNamespace(returncode=0, stdout=json.dumps(data))
        sensor = Sensor(runner=runner)
        a = sensor.read(now='2025-01-02T00:00:00Z')
        self.assertEqual(a['load']['utilisation'], {'cpu': .5, 'memory': .5})
        b = sensor.read(a, now='2025-01-09T00:00:00Z')
        self.assertEqual(b['events'], ['quiet'])
        current.update(uid='pod2', image='v2')
        c = sensor.read(b, now='2025-01-16T00:00:00Z')
        self.assertIn('upgrade', c['events'])
        self.assertIn('deploy', c['events'])
        current['namespace'] = False
        d = sensor.read(c, now='2025-01-17T00:00:00Z')
        self.assertIn('tenant_deletion', d['events'])
        current['namespace'] = True
        e = sensor.read(d, now='2025-01-18T00:00:00Z')
        self.assertIn('tenant_birth', e['events'])
        self.assertGreater(mood([a,b,c])['qualities']['volatility'], mood([a,b])['qualities']['volatility'])
        with self.assertRaises(ValueError): mood([c,a])

    def test_climate_changes_fate_and_observers(self):
        a,b = [Lineage('test', datetime(2025, 1, 1), seed=71) for _ in range(2)]
        for _ in range(60):
            a.step({'strain': 1, 'loss': 1, 'turbulence': 1, 'scars': 1})
            b.step({'steadiness': 1, 'abundance': 1, 'novelty': 1})
        self.assertNotEqual(a.artists[0].inner_critic, b.artists[0].inner_critic)
        self.assertNotEqual(a.artists[0].vitality, b.artists[0].vitality)
        self.assertNotEqual(a.reception.fashion, b.reception.fashion)
        self.assertNotEqual(a.reception.segments[0]['taste'], b.reception.segments[0]['taste'])
        self.assertNotEqual(a.reception.critics[0]['mood'], b.reception.critics[0]['mood'])

    def test_future_occasion_and_rejected_publicity(self):
        life = Lineage('test', datetime(2025, 1, 1))
        value = occasion('tenant_birth', 10)
        value['facts'] = 'CANARY'
        life.schedule(value)
        self.assertNotIn('CANARY', json.dumps(life.state()))
        self.assertEqual(life._work(life.artists[0])['kind'], 'study')
        self.assertEqual(len(life.occasions), 1)
        with self.assertRaises(ValueError): occasion('upgrade', 0, 'oops')
        with self.assertRaises(ValueError): programme({}, 'oops')
