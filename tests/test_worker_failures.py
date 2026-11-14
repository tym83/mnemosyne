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
