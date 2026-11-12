"""The atelier can be read from the console and as a static site, without touching it."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from mnemosyne.lineage import Lineage
from mnemosyne.viewer import Atelier, show_artists, show_work, site


class ViewerTests(unittest.TestCase):
    def test_console_and_site(self):
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        for _ in range(30):
            life.step({})
        a, w = next((a, w) for a in life.artists for w in a.catalogue)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lineage.json').write_text(json.dumps(life.state()))
            night = root/'nights'/f'{w["night"]:03d}'/w['id']
            night.mkdir(parents=True)
            (night/f'{w["id"]}.txt').write_text('Старый пруд.')
            (night/f'{w["id"]}.ru.txt').write_text('Перевод.')
            at = Atelier(root)
            out = io.StringIO()
            with redirect_stdout(out):
                show_artists(at)
                show_work(at, w['id'])
            self.assertIn(a.id, out.getvalue())
            self.assertIn('Старый пруд.', out.getvalue())
            self.assertIn('Перевод.', out.getvalue())
            before = (root/'lineage.json').read_bytes()
            site(at, root/'site')
            self.assertTrue((root/'site'/f'work-{w["id"]}.html').exists())
            self.assertIn('Старый пруд.', (root/'site'/f'work-{w["id"]}.html').read_text())
            self.assertEqual(before, (root/'lineage.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
