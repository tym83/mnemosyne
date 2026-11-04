import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from scheherazade import restore
from scheherazade.state.collect import archive
from scheherazade.weave import registry, DecodeError
from scheherazade.weave.codecs.v1 import surface, fountain, payload, frames


def fixture(cells=600):
    # Transport fixture, deliberately not represented as an artistic work.
    root = ET.Element('score-partwise')
    part = ET.SubElement(root, 'part', id='P1')
    for i in range(cells):
        measure = ET.SubElement(part, 'measure', number=str(i + 1))
        if i == 0:
            attributes = ET.SubElement(measure, 'attributes')
            ET.SubElement(attributes, 'divisions').text = '120'
        measure.extend(surface.notes((('A', 0, 2), ('E', 0, 3), ('G', 0, 3)), 120, 120, '3'))
    return root


def objects():
    return [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'shop'}},
            {'apiVersion': 'v1', 'kind': 'ConfigMap',
             'metadata': {'name': 'settings', 'namespace': 'shop'}, 'data': {'value': 'yes'}}]


class RestoreTests(unittest.TestCase):
    def test_archive_validation(self):
        data = archive(objects())
        self.assertEqual(archive(restore.read_archive(data)), data)
        for bad in (data + b'junk', data[:-8], archive([]), b'not zstd'):
            with self.assertRaises(ValueError):
                restore.read_archive(bad)

    def test_multiple_snapshots_are_not_silently_chosen(self):
        key = X25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            decoded = []
            for i in range(2):
                source = objects()
                source[1]['data']['value'] = str(i)
                envelope = payload.seal(archive(source), key.public_key(), context=fountain.DOMAIN)
                encoder = fountain.Encoder(envelope, len(envelope) + fountain.OVERHEAD, key)
                decoded.append(registry.Decoded('fountain-v1', encoder.frame(0)))
                (path / f'{i}.xml').write_text('test decoder input')
            with patch.object(registry, 'decode', side_effect=decoded):
                with self.assertRaisesRegex(ValueError, 'found 2'):
                    restore.recover_works(path, key)

    def test_fountain_music_after_loss_and_corruption(self):
        key = X25519PrivateKey.generate()
        data = archive(objects())
        envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            source = path / 'source.xml'
            surface.write(fixture(), source)
            capacity = surface.capacity(surface.read(source)) - 36
            encoder = fountain.Encoder(envelope, capacity, key)
            count = fountain.recommended_count(len(envelope), capacity)
            # Omit 30% of files, without deleting any generated work.
            survivors = random.Random(20261103).sample(range(count), count - (count * 3 + 9) // 10)
            for i in survivors:
                registry.encode_fountain(source, path / f'{i}.musicxml', encoder.frame(i), key)
            broken = path / 'broken.musicxml'
            broken.write_text('<broken>')
            recovered, actual, report = restore.recover_works(path, key)
            self.assertEqual(data, recovered)
            self.assertEqual(archive(actual), data)
            self.assertEqual(len(report['decoded']), len(survivors))
            self.assertEqual(len(report['rejected']), 2)
            with self.assertRaises(ValueError):
                restore.recover_works(path, X25519PrivateKey.generate())
            changed = surface.read(path / f'{survivors[0]}.musicxml')
            changed.find('.//measure').set('number', 'altered')
            surface.write(changed, path / 'tampered.musicxml')
            with self.assertRaises(DecodeError):
                registry.decode(path / 'tampered.musicxml', key)

    def test_legacy_and_version_dispatch(self):
        key = X25519PrivateKey.generate()
        data = archive(objects())
        envelope = payload.seal(data, key.public_key(), context=frames.DOMAIN)
        root = registry.mark(fixture(), registry.LEGACY)
        size = surface.capacity(root)
        count = (len(envelope) + size - frames.OVERHEAD - 1) // (size - frames.OVERHEAD)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for i in range(count):
                block = frames.pack(envelope, i, size, key, surface.context(root))
                surface.write(surface.encode(root, block), path / f'{i}.musicxml')
            # Duplicate work copies must not prevent recovery.
            (path / 'duplicate.musicxml').write_bytes((path / '0.musicxml').read_bytes())
            self.assertEqual(restore.recover_works(path, key)[0], data)
            changed = surface.read(path / '0.musicxml')
            changed.find('.//miscellaneous-field').text = json.dumps(
                {'school': 'romantic', 'method': 'nocturne', 'version': '999'})
            surface.write(changed, path / 'future.musicxml')
            with self.assertRaisesRegex(DecodeError, 'unsupported decoder'):
                registry.decode(path / 'future.musicxml', key)
            # Frozen algorithms do not call the current, mutable implementation.
            with patch('scheherazade.weave.surface.decode', side_effect=AssertionError):
                registry.decode(path / '0.musicxml', key)

    def test_order_retries_and_owner_rebinding(self):
        crd = {'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
               'metadata': {'name': 'widgets.example.org'},
               'spec': {'group': 'example.org', 'scope': 'Namespaced',
                        'names': {'kind': 'Widget'}, 'versions': [{'name': 'v1'}]}}
        ns, cm = objects()
        role = {'apiVersion': 'rbac.authorization.k8s.io/v1', 'kind': 'ClusterRole',
                'metadata': {'name': 'reader'}}
        cr = {'apiVersion': 'example.org/v1', 'kind': 'Widget',
              'metadata': {'name': 'widget', 'namespace': 'shop', 'ownerReferences': [
                  {'apiVersion': 'v1', 'kind': 'ConfigMap', 'name': 'settings', 'uid': 'old'}]}}
        class Backend:
            def __init__(self):
                self.applied = []
                self.failures = 1
            def owner_uid(self, owner, namespace):
                return 'new-uid'
            def apply(self, obj):
                if obj['kind'] == 'Widget' and self.failures:
                    self.failures -= 1
                    raise RuntimeError('dependency not ready')
                self.applied.append(obj)
        backend = Backend()
        source = [cr, role, cm, ns, crd]
        restore.apply_objects(source, backend, delay=0)
        self.assertEqual([o['kind'] for o in backend.applied],
                         ['CustomResourceDefinition', 'Namespace', 'ClusterRole', 'ConfigMap', 'Widget'])
        self.assertEqual(backend.applied[-1]['metadata']['ownerReferences'][0]['uid'], 'new-uid')
        self.assertEqual(cr['metadata']['ownerReferences'][0]['uid'], 'old')

    def test_apply_failure_does_not_advance_phase(self):
        class Backend:
            def apply(self, obj):
                self.kind = obj['kind']
                raise RuntimeError('unavailable')
        backend = Backend()
        with self.assertRaisesRegex(RuntimeError, 'phase 1 failed'):
            restore.apply_objects(objects(), backend, attempts=2, delay=0)
        self.assertEqual(backend.kind, 'Namespace')

    def test_cli_dry_run_never_contacts_cluster(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            key = path / 'key'
            key.write_bytes(X25519PrivateKey.generate().private_bytes_raw())
            output = path / 'restored'
            with patch('sys.argv', ['restore', '--works', str(path), '--key', str(key),
                '--output', str(output), '--apply', '--dry-run', '--kubeconfig', 'absent', '--context', 'absent']), \
                patch.object(restore, 'recover_works', return_value=(archive(objects()), objects(), {})), \
                patch.object(restore, 'Kubectl', side_effect=AssertionError('cluster contacted')):
                restore.main()
            self.assertEqual(restore.read_archive((output / 'archive.tar.zst').read_bytes()),
                             restore.read_archive(archive(objects())))
            self.assertEqual((output / 'manifests.yaml').stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
