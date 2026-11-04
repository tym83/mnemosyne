"""Compatibility across the project rename, including authenticated old XML."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.atelier import Atelier, GROUP, GROUP_ALIASES, crds, is_atelier_object
from mnemosyne.lineage import Lineage
from mnemosyne.restore import read_archive, recover_works
from mnemosyne.state.collect import archive
from mnemosyne.weave import DecodeError, registry
from mnemosyne.weave.codecs.v1 import fountain, payload, surface
from test_restore import fixture


class RenameTests(unittest.TestCase):
    def test_old_objects_and_new_manifests(self):
        life = Lineage('test', datetime(2025, 1, 1, tzinfo=timezone.utc))
        with tempfile.TemporaryDirectory() as tmp:
            atelier = Atelier('test', Path(tmp))
            atelier.lineage(life)
            self.assertTrue(all(o['apiVersion'] == 'mnemosyne.art/v1alpha1' for o in atelier.objects))
            self.assertTrue(all(c['spec']['group'] == GROUP for c in crds()))
            for group in GROUP_ALIASES:
                objects = deepcopy(atelier.objects)
                for obj in objects:
                    obj['apiVersion'] = group + '/v1alpha1'
                restored = read_archive(archive(objects))
                self.assertEqual(archive(restored), archive(objects))
                self.assertTrue(all(o['apiVersion'] == group + '/v1alpha1' for o in restored))
                self.assertEqual(Lineage.from_objects(restored, 'test').state(), life.state())
            unrelated = deepcopy(atelier.objects[0])
            unrelated['apiVersion'] = 'unrelated.example/v1alpha1'
            self.assertFalse(is_atelier_object(unrelated))

    def test_authenticated_old_and_new_decoder_names(self):
        key = X25519PrivateKey.generate()
        objects = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': 'test'}}]
        data = archive(objects)
        envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, name in enumerate(registry.FIELD_ALIASES):
                directory = root / str(index)
                directory.mkdir()
                source = directory / 'source.xml'
                surface.write(fixture(), source)
                capacity = surface.capacity(surface.read(source)) - 36
                encoder = fountain.Encoder(envelope, capacity, key)
                # Sign the original descriptor, never rename already signed XML.
                with patch.object(registry, 'FIELD', name):
                    for i in range(encoder.k):
                        registry.encode_fountain(source, directory / f'{i}.musicxml', encoder.frame(i), key)
                self.assertEqual(recover_works(directory, key)[0], data)
                with self.assertRaises(DecodeError):
                    registry.decode(directory / '0.musicxml', X25519PrivateKey.generate())

    def test_mixed_aliases_are_rejected(self):
        root = registry.mark(fixture(), registry.FOUNTAIN)
        misc = root.find('./identification/miscellaneous')
        ET.SubElement(misc, 'miscellaneous-field', name=registry.FIELD_ALIASES[1]).text = misc[0].text
        with self.assertRaisesRegex(DecodeError, 'duplicate'):
            registry.descriptor(root)
        with self.assertRaises(ValueError):
            registry.mark(root, registry.FOUNTAIN)

    def test_module_cli(self):
        for command in ([], ['restore'],):
            result = subprocess.run([sys.executable, '-m', 'mnemosyne', *command, '--help'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--works' if command else 'restore', result.stdout)
