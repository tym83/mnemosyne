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
            page = (root/'site'/f'work-{w["id"]}.html').read_text()
            self.assertIn('href="files/', page)
            self.assertTrue((root/'site'/'restore.html').exists())

    def test_the_restore_page_offers_every_carrier_of_a_continuous_life(self):
        import tarfile
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        for _ in range(30):
            life.step({})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lineage.json').write_text(json.dumps(life.state()))
            woven = root/'creators'/'leonia-0001'/'20261117T130414'/'woven'
            woven.mkdir(parents=True)
            (woven/'leonia-0001-w00001.variants.json').write_text('{}')
            site(Atelier(root), root/'site')
            page = (root/'site'/'restore.html').read_text()
            self.assertIn('creators/leonia-0001/20261117T130414/woven/leonia-0001-w00001.variants.json', page)
            with tarfile.open(root/'site'/'carriers.tar.gz') as archive:
                self.assertIn('carriers/creators/leonia-0001/20261117T130414/woven/leonia-0001-w00001.variants.json',
                              archive.getnames())

    def test_original_first_translation_on_demand(self):
        from mnemosyne.viewer import ru_block
        from mnemosyne.writing.memory import Memory, foreign
        german = 'Frau Kern legte den Gartenschlüssel auf meinen Tisch.'
        self.assertTrue(foreign(german))
        self.assertFalse(foreign('Фрау Керн положила ключ на стол.'))
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lineage.json').write_text(json.dumps(life.state()))
            memory = Memory(root)
            memory.put(german, 'Фрау Керн положила садовый ключ на мой стол.')
            memory.save()
            block = ru_block(Atelier(root), german)
            self.assertLess(block.index(german), block.index('Фрау Керн'))
            self.assertIn('class="ru"', block)


if __name__ == '__main__':
    unittest.main()


class ListenTests(unittest.TestCase):
    def test_a_sounded_work_can_be_heard_on_its_page(self):
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        for _ in range(30):
            life.step({})
        a, w = next((a, w) for a in life.artists for w in a.catalogue)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'lineage.json').write_text(json.dumps(life.state()))
            session = root/'creators'/a.id/'20261117T201500'
            result = session/'woven-render-draft-02'/'result'
            for rel in ('score.mp3', 'mv0/score.mp3', 'mv1/score.mp3'):
                (result/rel).parent.mkdir(parents=True, exist_ok=True)
                (result/rel).write_bytes(b'ID3')
            mp3 = ['woven-render-draft-02/result/mv0/score.mp3', 'woven-render-draft-02/result/mv1/score.mp3',
                   'woven-render-draft-02/result/score.mp3']
            (session/'notebook.json').write_text(json.dumps({
                'opus': w['id'], 'artist': a.id, 'status': 'accepted', 'final': 'draft-02', 'sounding_work': 'draft-02',
                'sketches': [{'id': 'draft-02', 'audio': {'local_mp3': mp3}}]}))
            (session/'woven').mkdir()
            (session/'woven'/f'{w["id"]}-notebook.variants.json').write_text('{}')
            # A later rejected session under the same opus must not hide the sounded one.
            later = root/'creators'/a.id/'20261118T090000'
            later.mkdir(parents=True)
            (later/'notebook.json').write_text(json.dumps({'opus': w['id'], 'artist': a.id, 'status': 'plan_rejected'}))
            site(Atelier(root), root/'site')
            page = (root/'site'/f'work-{w["id"]}.html').read_text()
            self.assertIn('id="listen"', page)
            self.assertLess(page.index('work.mp3'), page.index('mv0.mp3'))
            self.assertTrue((root/'site'/'audio'/w['id']/'work.mp3').exists())
            self.assertTrue((root/'site'/'audio'/w['id']/'mv1.mp3').exists())


class EnglishTests(unittest.TestCase):
    """The gallery speaks English at the root and Russian under ru/; texts keep their own language."""

    def atelier(self, tmp):
        life = Lineage('leonia', datetime(2025, 1, 1), seed=3)
        for _ in range(30):
            life.step({})
        a, w = next((a, w) for a in life.artists for w in a.catalogue)
        root = Path(tmp)
        (root/'lineage.json').write_text(json.dumps(life.state()))
        night = root/'nights'/f'{w["night"]:03d}'/w['id']
        night.mkdir(parents=True)
        (night/f'{w["id"]}.txt').write_text('An old pond.')
        (night/f'{w["id"]}.ru.txt').write_text('Старый пруд.')
        return root, a, w

    def test_the_english_pages_carry_no_cyrillic_and_the_russian_ones_live_under_ru(self):
        import re
        with tempfile.TemporaryDirectory() as tmp:
            root, a, w = self.atelier(tmp)
            out = site(Atelier(root), root/'site')
            pages = sorted(out.glob('*.html'))
            self.assertIn(out/'timeline.html', pages)
            for p in pages:
                text = p.read_text()
                if 'http-equiv="refresh"' in text:
                    # The manifesto and the Lexicon exist only in Russian: their root addresses lead to ru/.
                    self.assertTrue(p.name.startswith(('manifesto', 'lexicon', 'lex-')), p.name)
                    continue
                self.assertIn('<html lang="en">', text, p.name)
                chrome = re.sub(r'<style>.*?</style>', '', text, flags=re.S)
                self.assertIsNone(re.search('[А-Яа-яЁё]', chrome), (p.name, re.findall('[А-Яа-яЁё]+', chrome)[:5]))
                self.assertIn(f'href="ru/{p.name}"', text, p.name)
            work = (out/f'work-{w["id"]}.html').read_text()
            self.assertIn('An old pond.', work)
            self.assertNotIn('Старый пруд.', work)
            self.assertNotIn('id="trall"', work)
            ru = (out/'ru'/f'work-{w["id"]}.html').read_text()
            self.assertIn('<html lang="ru">', ru)
            self.assertIn('Старый пруд.', ru)
            self.assertIn(f'href="../work-{w["id"]}.html"', ru)
            self.assertIn('href="../files/', ru)
            self.assertNotIn('href="ru/', ru)
            # The Russian-only pages send their reader back to the English start, not into a loop.
            self.assertIn('href="../index.html" hreflang="en"', (out/'ru'/'manifesto.html').read_text())
            self.assertFalse((out/'ru'/'files').exists())
