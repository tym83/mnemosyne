"""The Translator renders composers' notebooks too; the gallery shows them in Russian with the original kept."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from mnemosyne.lineage import Lineage
from mnemosyne.viewer import Atelier, site
from mnemosyne.writing import memory, translator

IDEA = 'Ein Haus, in dem jede Tür eine andere Stille hat.'
REASONS = 'Die Idee ist zu glatt, sie sagt nicht, warum die Stille wehtut.'
OVERALL = 'Eine müde, fast zärtliche Trauer, die nicht klagt.'
HEARD = 'Das Cello trägt das Thema, aber die Pausen zerschneiden es zu oft.'
CORRECTION = 'Die Pausen im zweiten Teil kürzen und das Thema atmen lassen.'
METHOD = 'Weil die Glocken die Stille zählen.'
KEPT = 'Nur im Werk selbst bewahrt, nicht in einer Datei.'
PLAN = 'violoncello pizzicato sempre, harp in the low register'
NOT_PROSE = (PLAN, 'Romantic period | Brahms | Chamber', 'Arvo Pärt Tabula rasa recording')


def notebook(artist, opus):
    shade = {'shade': 'zärtlich und streng', 'why_mine': 'Weil ich lange allein gewohnt habe.',
             'how_it_shows': 'Lange Töne, die nicht aufgelöst werden.'}
    return {'version': 1, 'artist': artist, 'opus': opus, 'night': 0, 'status': 'accepted',
            'statement': {'idea': IDEA, 'emotions': ['Eine Sehnsucht nach dem verschlossenen Zimmer.']},
            'interrogation': [{'round': 0, 'statement': {'idea': IDEA},
                               'interrogation': {'verdict': 'accept', 'reasons': REASONS}}],
            'method': {'kind': 'school', 'school': 'tintinnabuli', 'sources': [NOT_PROSE[2]],
                       'concept': 'Drei Sätze, jeder ein anderer Raum desselben Hauses.',
                       'principle': '', 'transformation': '', 'reason': METHOD,
                       'notagen_prompt': NOT_PROSE[1], 'form': 'school'},
            'halftones': {'thought': shade, 'embodiment': shade, 'nuances': [], 'overall': OVERALL},
            'sketches': [{'id': opus + '-sketch-00', 'plan': {'note': PLAN}}],
            'entries': [{'step': 'listen:sketch', 'result': {'verdict': 'rewrite', 'reasons': HEARD,
                                                             'corrections': [CORRECTION], 'matters': False,
                                                             'quality': .6}},
                        {'step': 'listen:draft:0', 'result': {'verdict': 'accept',
                                                              'reasons': 'Jetzt atmet das Thema endlich frei.',
                                                              'corrections': [], 'matters': True, 'quality': .8}}],
            'verdict': {'verdict': 'accept', 'reasons': 'Jetzt atmet das Thema endlich frei.', 'corrections': []}}


def ask(system, prompt, schema, step, **kw):
    if schema is memory.Batch:
        return memory.Batch(items=['RU ' + t for t in json.loads(prompt)])
    if schema is translator.Translation:
        return translator.Translation(text='RU ' + prompt.split('\n\n', 1)[-1])
    raise AssertionError(schema)


class ComposerTranslationTests(unittest.TestCase):
    def atelier(self, tmp):
        life = Lineage('leonia', datetime(2025, 1, 1), seed=2)
        a = next(a for a in life.artists if a.art == 'music')
        a.language = 'de'
        w = life._work(a, observation=dict(feature=[.5] * 4, novelty=1, quality=.8, verdict='accept'))
        kept = notebook(a.id, w['id'])
        kept['halftones'] = {**kept['halftones'], 'overall': KEPT}
        w['process'] = {'composer': kept}
        root = Path(tmp)
        (root/'lineage.json').write_text(json.dumps(life.state()))
        night = root/'nights'/'000'/'session'
        night.mkdir(parents=True)
        (night/'notebook.json').write_text(json.dumps(notebook(a.id, f'{a.id}-w09999')))
        with patch('mnemosyne.literature.Writer.ask', side_effect=ask):
            memory.backfill(root, log=lambda *_: None)
        return root, a, w

    def test_backfill_translates_a_composers_notebook_prose_and_not_its_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, a, w = self.atelier(tmp)
            m = memory.Memory(root)
            for text in (IDEA, REASONS, OVERALL, HEARD, CORRECTION, METHOD, KEPT):
                self.assertEqual(m.get(text), 'RU ' + text)
            for text in NOT_PROSE:
                self.assertIsNone(m.get(text))

    def test_the_gallery_shows_a_composers_notebook_in_russian_with_the_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, a, w = self.atelier(tmp)
            out = site(Atelier(root), root/'site')
            page = (out/f'night-{a.id}-w09999.html').read_text()
            self.assertIn('Как композитор слушал свои черновики', page)
            self.assertIn('Полутона', page)
            for text in (HEARD, CORRECTION, OVERALL, METHOD):
                self.assertIn(text, page)
                self.assertIn('RU ' + text, page)
            self.assertIn('class="ru"', page)
            # The notebook kept only inside the work is shown on the work's page.
            work = (out/f'work-{w["id"]}.html').read_text()
            self.assertIn('RU ' + KEPT, work)


if __name__ == '__main__':
    unittest.main()
