"""The continuous life of the atelier: no nights, one process per creator, arrivals one by one."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.operator import life as living


class Session:
    made = []

    def __init__(self, life, aid, root):
        self.work_id, self.root, self.sketches = f'{aid}-{root.name}', Path(root), []
        self.record = {'status': 'searching', 'idea': 'Слова про море, которое помнит каждого, кто уходил.'}
        self.root.mkdir(parents=True, exist_ok=True)
        Session.made.append((aid, time.monotonic()))

    def run(self, *a, **k):
        self.record['status'] = 'accepted'
        return self.record


class LifeTests(unittest.TestCase):
    def test_the_atelier_begins_with_one_creator(self):
        with tempfile.TemporaryDirectory() as tmp:
            life = living.Life({'atelier': 'a', 'inventory': []}, Path(tmp), X25519PrivateKey.generate(), None, 'ns')
            self.assertEqual(len(life.life.artists), 1)

    def test_creators_arrive_one_by_one_over_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            life = living.Life({'atelier': 'a', 'inventory': []}, Path(tmp), X25519PrivateKey.generate(), None, 'ns')
            arrivals = []
            for day in range(40):
                life.life.step({})
                arrivals.append(len(life.life.artists))
            self.assertGreater(arrivals[-1], 1)
            self.assertLess(arrivals[0], arrivals[-1])
            self.assertTrue(all(b - a <= 2 for a, b in zip(arrivals, arrivals[1:])))

    def test_each_creator_works_on_their_own_and_rests(self):
        Session.made = []
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(living, 'rest_seconds', return_value=3600), \
             patch.object(living, 'start_delay', return_value=0), \
             patch.object(living.Life, 'carry', return_value=None), \
             patch.object(living.Life, 'publish', return_value=None):
            life = living.Life({'atelier': 'a', 'inventory': []}, Path(tmp), X25519PrivateKey.generate(), None, 'ns',
                               night_factory=Session, writer_factory=Session)
            for _ in range(15):
                life.life.step({})
            life.spawn()
            time.sleep(1)
            life.stop.set()
            for thread in life.threads.values():
                thread.join(10)
            working = {a.id for a in life.life.working()}
            # Every working creator has started a work of their own, and nobody worked twice: they rest.
            self.assertTrue(working)
            self.assertEqual({aid for aid, _ in Session.made} & working, working)
            self.assertEqual(len(Session.made), len({aid for aid, _ in Session.made}))

    def test_a_new_artifact_carries_the_cluster_at_once(self):
        from mnemosyne.state.ledger import Ledger
        from mnemosyne.operator.worker import margins
        with tempfile.TemporaryDirectory() as tmp:
            key = X25519PrivateKey.generate()
            life = living.Life({'atelier': 'a', 'inventory': []}, Path(tmp), key, None, 'ns')
            objects = [{'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': f'c{i}', 'namespace': 'n'},
                        'data': {'k': 'v' * 40}} for i in range(5)]
            ledger = Ledger(Path(tmp)/'ledger')
            ledger.observe(objects, '2026-11-15T00:00:00+00:00', key.public_key())
            ledger.save()
            composer = next(a for a in life.life.artists if a.art == 'music')
            sources = margins(life.life, Path(tmp)/'w', 2, only=composer.id)
            report = life.carry(sources, [], Path(tmp)/'woven')
            self.assertTrue(report['carriers'])
            self.assertTrue(report['frame_decode_verified'])

    def test_a_much_smaller_state_supersedes_an_unfinished_snapshot(self):
        from mnemosyne.state.ledger import Ledger
        with tempfile.TemporaryDirectory() as tmp:
            key = X25519PrivateKey.generate()
            ledger = Ledger(Path(tmp))
            big = [{'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': f'c{i}', 'namespace': 'n'},
                    'data': {'k': f'{i}' + 'x' * 4000}} for i in range(40)]
            first = ledger.observe(big, '2026-11-15T00:00:00+00:00', key.public_key())
            small = big[:3]
            second = ledger.observe(small, '2026-11-15T01:00:00+00:00', key.public_key())
            self.assertIsNotNone(second)
            self.assertEqual(second['kind'], 'keyframe')
            self.assertEqual([p['id'] for p in ledger.pending()], [second['id']])
            self.assertEqual(first['superseded'], second['id'])

    def test_an_interrupted_work_resumes_without_asking_again(self):
        from mnemosyne.literature import Writer
        from pydantic import BaseModel

        class Answer(BaseModel):
            text: str
        notebook = []
        writer = Writer(notebook, backend='none')
        writer.replay = {'idea': {'text': 'море'}}
        self.assertEqual(writer.ask('s', 'p', Answer, 'idea').text, 'море')
        self.assertTrue(notebook[-1]['replayed'])


if __name__ == '__main__':
    unittest.main()


class RestoreForNewClusterTests(unittest.TestCase):
    def test_a_claim_gets_a_fresh_volume(self):
        from mnemosyne.restore import for_new_cluster
        pvc = {'apiVersion': 'v1', 'kind': 'PersistentVolumeClaim',
               'metadata': {'name': 'w', 'namespace': 'n', 'annotations': {'pv.kubernetes.io/bind-completed': 'yes'}},
               'spec': {'volumeName': 'pvc-old', 'resources': {'requests': {'storage': '1Gi'}}}}
        out = for_new_cluster(pvc)
        self.assertNotIn('volumeName', out['spec'])
        self.assertNotIn('pv.kubernetes.io/bind-completed', out['metadata']['annotations'])


class LightenTests(unittest.TestCase):
    def test_a_huge_notebook_keeps_a_reference_to_its_process(self):
        from mnemosyne.operator.kube import lighten, LIMIT
        import json
        with tempfile.TemporaryDirectory() as tmp:
            body = {'kind': 'Notebook', 'metadata': {'name': 'n'},
                    'spec': {'opus': 'w', 'process': {'entries': ['x' * 1000] * 1000}}}
            light = lighten(body, tmp)
            self.assertLess(len(json.dumps(light)), LIMIT)
            ref = light['spec']['process']
            self.assertEqual(json.loads((Path(tmp)/ref['file']).read_text()), body['spec']['process'])


class BudgetTests(unittest.TestCase):
    def test_spending_is_recorded_and_summed_for_the_month(self):
        import os
        from mnemosyne.models import Endpoint, spend, spent_this_month
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, MNEMO_SPEND_LOG=f'{tmp}/s.jsonl'):
            e = Endpoint(backend='anthropic', base_url='https://x/v1', model='m', price_in=4, price_out=20)
            spend(e, {'input_tokens': 1_000_000, 'output_tokens': 100_000})
            self.assertAlmostEqual(spent_this_month(f'{tmp}/s.jsonl'), 6.0)
