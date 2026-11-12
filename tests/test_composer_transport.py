"""Composer nights carry cluster state, never the atelier's own history."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.atelier import obj
from mnemosyne.music.composer import Night
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.restore import recover_works
from mnemosyne.state import ledger as ledger_module
from mnemosyne.weave import fountain, payload, registry, school_series, schools, surface


def plan_for(name):
    return json.loads(Path(f'src/mnemosyne/music/schools/plans/{name}.json').read_text())


def cluster(value='one'):
    return [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'shop'}},
            {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'settings', 'namespace': 'shop'},
             'data': {'mode': value}},
            {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'web', 'namespace': 'shop'},
             'spec': {'replicas': 2, 'selector': {'matchLabels': {'app': 'web'}},
                      'template': {'metadata': {'labels': {'app': 'web'}},
                                   'spec': {'containers': [{'name': 'web', 'image': 'nginx:1.27'}]}}}},
            obj('Notebook', 'fixture', {'entries': [{'idea': 'never payload'}]})]


def night(root, state, ledger_root, date, works=16, accepted=True):
    plan = plan_for('drone')
    root.mkdir(parents=True)
    path = root/'source.musicxml'
    SCHOOLS['drone'].compose(plan, plan['seed']).write('musicxml', fp=path)
    n = Night.__new__(Night)
    n.root, n.studio, n.sound = root, Mock(), True
    n.life = Mock(schools={}, date=Mock(return_value=date))
    n.record = {'verdict': {'verdict': 'accept' if accepted else 'rewrite'}, 'final': 'w-0'}
    n.sketches = [{'id': f'w-{i}', 'stage': f's-{i}', 'plan': plan, 'score': path.name, 'form': 'school'}
                  for i in range(works)]
    n.cluster_state, n.ledger_root = state, ledger_root
    n.studio.run.return_value = {}
    return n


class ComposerTransportTests(unittest.TestCase):
    def test_cluster_restored_from_scores_and_atelier_is_not_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = X25519PrivateKey.generate()
            n = night(tmp/'n1', cluster(), tmp/'ledger', '2025-07-01T00:00:00')
            n.backup(key)
            report = n.record['backup']
            self.assertEqual(report['pending_pieces'], 0)
            self.assertEqual(n.record['status'], 'complete')
            data, objects, rep = recover_works(tmp/'n1/woven', key)
            self.assertEqual({o['kind'] for o in objects}, {'Namespace', 'ConfigMap', 'Deployment'})
            self.assertEqual(data, ledger_module.pack(ledger_module.members(cluster())))
            self.assertEqual(rep['moment']['moment'], '2025-07-01T00:00:00')
            woven = next((tmp/'n1/woven').glob('*.musicxml'))
            tree = surface.read(woven)
            field = tree.find('.//miscellaneous-field[@name="mnemosyne.catalogue"]')
            self.assertEqual(json.loads(field.text)[0]['backup']['carrier'], woven.stem)
            field.text = '{}'
            surface.write(tree, tmp/'tampered.musicxml')
            with self.assertRaises(ValueError):
                registry.decode(tmp/'tampered.musicxml', key)

    def test_pieces_accumulate_across_nights_and_restore_chooses_a_moment(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = X25519PrivateKey.generate()
            led = tmp/'ledger'
            # Night 1: one work starts the keyframe but cannot make it loss-tolerant.
            night(tmp/'n1', cluster('one'), led, '2025-07-01T00:00:00', works=1).backup(key)
            first = ledger_module.Ledger(led).pending()
            self.assertEqual(len(first), 1)
            carried = first[0]['carried']
            # Night 2: unchanged cluster; new works continue the same piece after its last frame.
            n2 = night(tmp/'n2', cluster('one'), led, '2025-07-02T00:00:00', works=16)
            n2.backup(key)
            self.assertIsNone(n2.record['backup']['observed'])
            meta = json.loads(next((tmp/'n2/woven').glob('*.catalogue.json')).read_text())
            self.assertEqual(meta[0]['backup']['catalogue']['body']['first'], carried)
            self.assertFalse(ledger_module.Ledger(led).pending())
            # Night 3: one change becomes a delta piece.
            n3 = night(tmp/'n3', cluster('two'), led, '2025-07-03T00:00:00', works=16)
            n3.backup(key)
            self.assertEqual(n3.record['backup']['observed']['kind'], 'delta')
            works = tmp/'all'
            works.mkdir()
            for d in ('n1', 'n2', 'n3'):
                for p in (tmp/d/'woven').glob('*.musicxml'):
                    (works/f'{d}-{p.name}').write_bytes(p.read_bytes())
            _, latest, rep = recover_works(works, key)
            self.assertEqual(next(o for o in latest if o['kind'] == 'ConfigMap')['data']['mode'], 'two')
            self.assertEqual(len(rep['moment']['chain']), 2)
            _, earlier, rep = recover_works(works, key, at='2025-07-02T12:00:00')
            self.assertEqual(next(o for o in earlier if o['kind'] == 'ConfigMap')['data']['mode'], 'one')

    def test_without_cluster_state_nothing_is_carried(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = night(Path(tmp)/'n', None, Path(tmp)/'ledger', '2025-07-01T00:00:00', accepted=False)
            n.backup(X25519PrivateKey.generate())
            self.assertIn('no cluster state', n.record['backup']['reason'])

    def test_without_capacity_the_piece_waits_in_the_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            n = night(Path(tmp)/'n', cluster(), Path(tmp)/'ledger', '2025-07-01T00:00:00', works=0, accepted=False)
            n.backup(X25519PrivateKey.generate())
            self.assertEqual(n.record['backup']['pending_pieces'], 1)
            self.assertTrue(any((Path(tmp)/'ledger/envelopes').iterdir()))

    def test_symphony_dynamics_registry_authenticates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture.musicxml'
            plan = plan_for('additive')
            SCHOOLS['additive'].compose(plan, plan['seed']).write('musicxml', fp=path)
            root = registry.mark(schools.prepare(surface.read(path), 'symphony'),
                                 ('symphony', 'dynamics-fountain', '2'))
            key = X25519PrivateKey.generate()
            env = payload.seal(b'transport fixture', key.public_key(), context=fountain.DOMAIN)
            encoder = fountain.Encoder(env, 128, key)
            frame = encoder.frame(0)
            surface.write(school_series.encode(root, frame, key), path)
            self.assertEqual(registry.decode(path, key).frame, [frame])


if __name__ == '__main__':
    unittest.main()
