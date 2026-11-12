"""Actual score transport; run music fixtures in a studio pod."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.music.composer import Night
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.restore import recover_works
from mnemosyne.weave import registry, schools, school_series, surface, fountain, payload
from mnemosyne.weave.school_audit import plan_for
from mnemosyne.atelier import obj


class ComposerTransportTests(unittest.TestCase):
    def test_notebook_and_lives_recovered_from_scores_without_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = plan_for('additive')
            path = root/'source.musicxml'
            SCHOOLS['additive'].compose(plan, plan['seed']).write('musicxml', fp=path)
            night = Night.__new__(Night)
            night.root = root
            night.studio = Mock()
            night.sound = True
            night.record = {'verdict': {'verdict': 'accept'}, 'final': 'fixture-sketch-15'}
            night.sketches = [{'id': f'fixture-sketch-{i}', 'stage': f'fixture-{i}', 'plan': plan,
                               'score': path.name, 'form': 'school'} for i in range(16)]
            night.objects = [obj('Notebook', 'fixture', {'entries': [{'idea': 'fixture', 'verdict': 'accept'}]}),
                             obj('Biography', 'fixture', {'chapters': [{'text': 'fixture chapter'}]})]
            key = X25519PrivateKey.generate()
            night.backup(key)
            report = night.record['backup']
            self.assertTrue(report['archive_recovered'])
            self.assertTrue(report['post_render_decode_verified'])
            restored, objects, _ = recover_works(root/'woven', key)
            self.assertEqual(restored, (root/'state.tar.zst').read_bytes())
            self.assertTrue({'Notebook', 'Biography', 'CustomResourceDefinition', 'Namespace'} <= {o['kind'] for o in objects})
            self.assertEqual(night.studio.run.call_args.args[0]['action'], 'woven')
            night.studio.run.assert_called_once()
            self.assertEqual(night.studio.run.call_args.args[0]['xml'],
                             (root/'woven/fixture-sketch-15.musicxml').read_text())
            self.assertEqual(night.record['sounding_work'], 'fixture-sketch-15')
            woven = next((root/'woven').glob('*.musicxml'))
            tree = surface.read(woven)
            field = tree.find('.//miscellaneous-field[@name="mnemosyne.catalogue"]')
            self.assertIn('fixture-sketch', field.text)
            mapping = json.loads(field.text)
            self.assertEqual(mapping[0]['backup']['carrier'], woven.stem)
            field.text = '{}'
            changed = root/'tampered.musicxml'
            surface.write(tree, changed)
            with self.assertRaises(ValueError):
                registry.decode(changed, key)

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

    def test_no_capacity_preserves_pending_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            night = Night.__new__(Night)
            night.root = Path(tmp)
            night.record = {}
            night.sketches = []
            night.objects = [obj('Notebook', 'fixture', {'entries': ['retained']})]
            night.backup(X25519PrivateKey.generate())
            self.assertEqual(night.record['status'], 'backup_pending_capacity')
            self.assertFalse(night.record['backup']['archive_recovered'])
            self.assertTrue((night.root/'pending-envelope.bin').is_file())


if __name__ == '__main__':
    unittest.main()
