import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from mnemosyne.artist import SelfPortrait, Statement
from mnemosyne.drawing.sheets import Drawing, Look, Path_, Sheet, work


class CorrectionLoop(unittest.TestCase):
    def test_exemplar_large_correction_and_unchanged_feedback(self):
        def fields(model):
            return {name: {} if field.annotation is dict else [] if field.annotation == list[str] else 'test'
                    for name, field in model.model_fields.items()}

        rec = {'portrait': fields(SelfPortrait), 'statement': fields(Statement), 'halftones': {},
               'interrogation': [{'interrogation': {'cliches_found': [], 'weak_answers': []}}]}
        plan = Path_(sheets=[Sheet(kind='study', title='Test', what_it_shows='', why_this_sheet='',
                                  view='', light='', style='etching')], order_of_search='')
        requests = []

        def ask(system, prompt, schema, step, **kwargs):
            requests.append((step, prompt, kwargs))
            if schema is Path_:
                return plan
            if schema is Drawing:
                return Drawing(script="reset('etching')", what_i_changed='')
            return Look(i_see='test', works=[], fails=[], correction='detail', leave_it=True,
                        composition_settled=False, correction_scale='detail', weaker_than_master='space')

        def draw(script, png, *args, **kwargs):
            Image.new('RGB', (300, 200), 'white').save(png)
            return ''

        with tempfile.TemporaryDirectory() as tmp, patch('mnemosyne.drawing.sheets.Writer') as writer, \
                patch('mnemosyne.drawing.sheets.draw', side_effect=draw):
            writer.return_value.ask.side_effect = ask
            result = work(rec, Path(tmp), drafts=3)
        looks = [r for r in requests if ':look' in r[0]]
        self.assertEqual(len(looks), 3)
        self.assertTrue(all(len(r[2]['images']) == 2 for r in looks))
        draft2 = next(r[1] for r in requests if r[0] == 'sheet1:draft2')
        draft3 = next(r[1] for r in requests if r[0] == 'sheet1:draft3')
        self.assertIn('Композиция не найдена', draft2)
        self.assertIn('почти не изменился', draft3)
        self.assertTrue(result['sheets'][0]['drafts'][1]['difference']['barely_changed'])
        self.assertFalse(result['sheets'][0]['drafts'][0]['look']['leave_it'])
