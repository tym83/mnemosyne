"""The continuous life of the atelier: no nights, one process per creator, arrivals one by one."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
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

    def render_final(self, woven):
        self.record['sounding_work'] = 'final'
        self.rendered_from = woven

    def save(self):
        pass


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

    def test_an_accepted_composition_sounds_after_it_carries(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(living.Life, 'carry', return_value=None):
            life = living.Life({'atelier': 'a', 'inventory': []}, Path(tmp), X25519PrivateKey.generate(), None, 'ns',
                               night_factory=Session, writer_factory=Session)
            composer = next(a for a in life.life.artists if a.art == 'music')
            life.work(composer)
            self.assertIn(f'sounded {composer.id}', (Path(tmp)/'life.log').read_text())

    def test_woven_scores_are_named_as_the_renderer_looks_them_up(self):
        sketch = {'id': 'draft-02', 'carriers': [{'movement_index': 0}, {'movement_index': 1}]}
        self.assertEqual(living.carrier_name(sketch, 1, sketch['carriers'][1]), 'draft-02-mv2')
        lone = {'id': 'draft-01', 'score': 'x'}
        self.assertEqual(living.carrier_name(lone, 0, {'score': 'x'}), 'draft-01')

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

    def test_any_large_field_moves_to_the_volume(self):
        from mnemosyne.operator.kube import lighten, LIMIT
        import json
        with tempfile.TemporaryDirectory() as tmp:
            body = {'kind': 'Notebook', 'metadata': {'name': 'n'},
                    'spec': {'opus': 'w', 'entries': [{'answer': 'y' * 1000}] * 900}}
            light = lighten(body, tmp)
            self.assertLess(len(json.dumps(light)), 100_000)
            self.assertEqual(light['spec']['opus'], 'w')


class BudgetTests(unittest.TestCase):
    def test_spending_is_recorded_and_summed_for_the_month(self):
        import os
        from mnemosyne.models import Endpoint, spend, spent_this_month
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, MNEMO_SPEND_LOG=f'{tmp}/s.jsonl'):
            e = Endpoint(backend='anthropic', base_url='https://x/v1', model='m', price_in=4, price_out=20)
            spend(e, {'input_tokens': 1_000_000, 'output_tokens': 100_000})
            self.assertAlmostEqual(spent_this_month(f'{tmp}/s.jsonl'), 6.0)


class WriterMarginTests(unittest.TestCase):
    def test_a_writers_margin_is_their_own_words_and_carries(self):
        import os
        from mnemosyne.writing.margins import page
        from mnemosyne.weave import variants
        texts = ['Было то или не было, а коли не было, так будет: сказка ни у времени, ни у попа дозволения '
                 'не спрашивает. В большом городе была слобода жестянщиков, кастрюли и лейки, светильники и '
                 'воронки, переплётчик сшивал книги, которых никто не читал, коваль пел фаду скверно, воробьи '
                 'перебирались на другую крышу, жестянщик Мануэл, три сына, бабушка Роза лущила фасоль у очага.']
        markup = page(texts, 'w:1')
        entries = [{'id': '/m', 'markup': markup}]
        size = variants.capacity(entries)
        self.assertGreater(size, 150)
        words = set(w.lower() for t in texts for w in __import__('re').findall(r'\w{3,}', t))
        options = {o for _, opts in variants.places(markup)[0] for o in opts}
        self.assertTrue(options <= words)
        frames = [os.urandom(192) for _ in range((size - variants.OVERHEAD - 8) // 192)]
        key = X25519PrivateKey.generate()
        volume = variants.encode_many(entries, frames, key)
        self.assertEqual(variants.decode_many(volume, key), frames)


class PublishTests(unittest.TestCase):
    def test_an_existing_object_loses_keys_its_new_spec_no_longer_has(self):
        from kubernetes.client.exceptions import ApiException
        from mnemosyne.operator import kube
        stored = {'apiVersion': 'mnemosyne.art/v1alpha1', 'kind': 'Notebook',
                  'metadata': {'name': 'n', 'resourceVersion': '7'},
                  'spec': {'opus': 'w', 'process': {'composer': {'entries': ['x'] * 10}}}}

        class Custom:
            def create_namespaced_custom_object(self, *a):
                raise ApiException(status=409)

            def get_namespaced_custom_object(self, *a):
                return json.loads(json.dumps(stored))

            def replace_namespaced_custom_object(self, *a):
                stored.clear()
                stored.update(a[-1])

        body = {'apiVersion': 'mnemosyne.art/v1alpha1', 'kind': 'Notebook', 'metadata': {'name': 'n'},
                'spec': {'opus': 'w', 'process': {'sha256': 'abc', 'bytes': 3}}}
        with patch('kubernetes.client.CustomObjectsApi', return_value=Custom()):
            kube.publish(None, 'mnemosyne', [body])
        self.assertEqual(stored['spec']['process'], {'sha256': 'abc', 'bytes': 3})
        self.assertEqual(stored['metadata']['resourceVersion'], '7')

    def test_keys_the_atelier_does_not_publish_stay_with_their_owner(self):
        from kubernetes.client.exceptions import ApiException
        from mnemosyne.operator import kube
        stored = {'kind': 'Atelier', 'metadata': {'name': 'a'},
                  'spec': {'runtime': {'window': {'kind': 'continuous'}}, 'lineage': {'old': 1}}}

        class Custom:
            def create_namespaced_custom_object(self, *a):
                raise ApiException(status=409)

            def get_namespaced_custom_object(self, *a):
                return json.loads(json.dumps(stored))

            def replace_namespaced_custom_object(self, *a):
                stored.clear()
                stored.update(a[-1])

        body = {'apiVersion': 'mnemosyne.art/v1alpha1', 'kind': 'Atelier', 'metadata': {'name': 'a'},
                'spec': {'lineage': {'new': 2}}}
        with patch('kubernetes.client.CustomObjectsApi', return_value=Custom()):
            kube.publish(None, 'mnemosyne', [body])
        self.assertEqual(stored['spec'], {'runtime': {'window': {'kind': 'continuous'}}, 'lineage': {'new': 2}})


class GistTests(unittest.TestCase):
    def test_a_former_work_is_named_by_its_title_and_first_sentence(self):
        from mnemosyne.artist import gist
        work = json.dumps({'title': 'Lock-In', 'idea': 'A span falls by courtesy. Then forty players cross.'})
        self.assertEqual(gist(work), '«Lock-In»: A span falls by courtesy.')
        self.assertEqual(gist(json.dumps({'idea': 'One. Two.'})), 'One.')
        self.assertEqual(gist('plain text'), 'plain text')
