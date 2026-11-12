"""A lived history moves into a studio volume once, keeps its shape, and is shown read-only."""
import hashlib
import json
import tarfile
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from mnemosyne.history import export, import_
from mnemosyne.lineage import Lineage
from mnemosyne.viewer import Atelier, site


def lived(root: Path):
    root.mkdir(parents=True)
    life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
    for _ in range(20):
        life.step({})
    (root/'lineage.json').write_text(json.dumps(life.state()))
    a, w = next((a, w) for a in life.artists for w in a.catalogue)
    night = root/'nights'/f'{w["night"]:03d}'/w['id']
    night.mkdir(parents=True)
    (night/f'{w["id"]}.txt').write_text('Старый пруд.')
    (root/'nights'/'ledger').mkdir()
    (root/'nights'/'ledger'/'ledger.json').write_text(json.dumps({'state': {}, 'pieces': []}))
    (root/'keys').mkdir()
    (root/'keys'/'owner.key').write_bytes(b'\0' * 32)
    return w


class HistoryTests(unittest.TestCase):
    def test_export_import_keeps_shape_never_keys_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            w = lived(tmp/'year')
            digest = export(tmp/'year', tmp/'h.tar.gz')
            with tarfile.open(tmp/'h.tar.gz') as tar:
                names = tar.getnames()
            self.assertIn('lineage.json', names)
            self.assertIn('ledger/ledger.json', names)
            self.assertFalse(any('key' in n for n in names))
            into = tmp/'works'/'leonia-atelier'
            self.assertTrue(import_(str(tmp/'h.tar.gz'), digest, into)['imported'])
            self.assertTrue((into/'ledger'/'ledger.json').exists())
            self.assertFalse(import_(str(tmp/'h.tar.gz'), digest, into)['imported'])
            with self.assertRaises(ValueError):
                import_(str(tmp/'h.tar.gz'), '0' * 64, tmp/'works'/'other')
            out = site(Atelier(into), tmp/'site')
            self.assertIn('Старый пруд.', (out/f'work-{w["id"]}.html').read_text())
            self.assertTrue((out/'restore.html').exists())

    def test_archive_with_keys_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp/'lineage.json').write_text('{}')
            (tmp/'owner.key').write_bytes(b'\0')
            with tarfile.open(tmp/'bad.tar.gz', 'w:gz') as tar:
                tar.add(tmp/'lineage.json', 'lineage.json')
                tar.add(tmp/'owner.key', 'keys/owner.key')
            digest = hashlib.sha256((tmp/'bad.tar.gz').read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                import_(str(tmp/'bad.tar.gz'), digest, tmp/'works'/'x')


if __name__ == '__main__':
    unittest.main()
