import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mnemosyne.models import Endpoint
from mnemosyne.operator import worker


class FakeNight:
    def __init__(self, life, artist_id, root, *a, **k):
        self.work_id, self.record, self.objects, self.sketches = artist_id + '-w0', {'status': 'searching'}, [], []
        Path(root).mkdir(parents=True, exist_ok=True)

    def run(self, *a, **k):
        raise RuntimeError('sketch-plan:1: all configured endpoints failed')


class FakeWriter:
    ran = []

    def __init__(self, life, artist_id, root, *a, **k):
        self.work_id, self.record = artist_id + '-w0', {'status': 'searching'}
        self.id = artist_id

    def run(self):
        FakeWriter.ran.append(self.id)
        self.record['status'] = 'accepted'
        return self.record


class Models:
    def route(self, role):
        return [('api', Endpoint(backend='anthropic', base_url='https://api.example/v1', model='m'))]


class WorkerFailureTests(unittest.TestCase):
    def test_one_creator_failing_does_not_stop_the_night(self):
        FakeWriter.ran = []
        with tempfile.TemporaryDirectory() as tmp, \
             patch('mnemosyne.models.Models.load', return_value=Models()), \
             patch('mnemosyne.music.composer.Night', FakeNight), \
             patch('mnemosyne.writing.night.WriterNight', FakeWriter), \
             patch('mnemosyne.reception.Reception.write_words', create=True), \
             patch('mnemosyne.lineage.Lineage.write_words'), \
             patch.object(worker, 'weave', return_value={'phase': 'Verified', 'pending_pieces': 0}):
            records, report = worker.run({'mode': 'API', 'atelier': 'a', 'render': False},
                                         Path(tmp)/'night', None, [])
        self.assertTrue(FakeWriter.ran, 'writers still work after a composer fails')
        self.assertTrue(report['failed_creators'])


if __name__ == '__main__':
    unittest.main()


class MarginTests(unittest.TestCase):
    def test_every_composer_writes_margins_that_carry(self):
        from datetime import datetime
        from mnemosyne.lineage import Lineage
        from mnemosyne.weave import schools as ws, surface
        life = Lineage('t', datetime(2025, 1, 1))
        with tempfile.TemporaryDirectory() as tmp:
            sources = worker.margins(life, Path(tmp), per_creator=2)
            composers = [a for a in life.working() if a.art == 'music']
            self.assertEqual(len(sources), 2 * len(composers))
            name, path, school, extra = sources[0]
            self.assertFalse(extra['final'])
            root = ws.prepare(surface.read(path), school)
            self.assertTrue(any(d.get('id', '').startswith(ws.PREFIX) for d in root.iter('direction')))


class CrdReferenceTests(unittest.TestCase):
    def test_a_type_definition_is_kept_by_reference(self):
        from mnemosyne.operator.kube import crd_reference, SPEC_SHA
        from mnemosyne.restore import ordered
        crd = {'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
               'metadata': {'name': 'widgets.example.com', 'resourceVersion': '9', 'uid': 'u'},
               'spec': {'group': 'example.com', 'scope': 'Namespaced',
                        'names': {'kind': 'Widget', 'plural': 'widgets'},
                        'versions': [{'name': 'v1', 'served': True, 'storage': True,
                                      'schema': {'openAPIV3Schema': {'type': 'object', 'x': 'y' * 5000}}}]}}
        ref = crd_reference(crd)
        self.assertLess(len(json.dumps(ref)), 800)
        self.assertEqual(len(ref['metadata']['annotations'][SPEC_SHA]), 64)
        widget = {'apiVersion': 'example.com/v1', 'kind': 'Widget', 'metadata': {'name': 'w', 'namespace': 'n'}}
        objects, stage = ordered([widget, ref])
        self.assertEqual(stage(objects[0]), 0)
