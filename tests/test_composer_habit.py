"""A composer sees the forms and ensembles of their own latest works before choosing the next."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from mnemosyne.music.composer import Night, SchoolMethod, SymphonyMethod, form_fatigue


class HabitTests(unittest.TestCase):
    def test_latest_forms_and_ensembles_come_from_the_composers_notebooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions = Path(tmp)
            for stamp, record in (
                    ('1', {'status': 'accepted', 'final': 'd', 'sketches': [
                        {'id': 'd', 'form': 'school', 'plan': {'school': 'fugue', 'ensemble': 'string_quartet'}}]}),
                    ('2', {'status': 'failed'}),
                    ('3', {'status': 'accepted', 'final': 'd', 'method': {'school': 'classical'}, 'sketches': [
                        {'id': 'd', 'form': 'symphony', 'plan': {'movements': []}}]}),
                    ('4', {'status': 'searching'})):
                (sessions/stamp).mkdir()
                (sessions/stamp/'notebook.json').write_text(json.dumps(record))
            habit = Night.habit(SimpleNamespace(root=sessions/'4'))
            self.assertEqual(habit, [
                {'form': 'symphony', 'ensemble': 'symphony_orchestra', 'school': 'classical', 'verdict': 'accepted'},
                {'form': 'school', 'ensemble': 'string_quartet', 'school': 'fugue', 'verdict': 'accepted'}])



class FormFatigueTests(unittest.TestCase):
    def test_three_symphonies_running_tire_the_ear(self):
        habit = [{'form': 'symphony'}] * 3 + [{'form': 'school'}]
        self.assertEqual(form_fatigue(habit), 'symphony')
        self.assertIsNone(form_fatigue([{'form': 'symphony'}, {'form': 'school'}, {'form': 'symphony'}]))
        self.assertIsNone(form_fatigue([{'form': 'symphony'}] * 2))

    def test_a_tired_composer_can_only_answer_with_the_other_form(self):
        base = dict(school='fugue', sources=[], principle='', transformation='', concept='', reason='',
                    notagen_prompt='')
        SchoolMethod(kind='school', form='school', **base)
        with self.assertRaises(ValueError):
            SchoolMethod(kind='school', form='symphony', **base)
        with self.assertRaises(ValueError):
            SchoolMethod(kind='cross', form='school', **base)
        SymphonyMethod(kind='cross', form='symphony', **base)


class SlashKeyTests(unittest.TestCase):
    def test_a_key_holding_a_path_is_published_back_to_the_same_key(self):
        from mnemosyne.weave import variants
        record = {'worker_logs': {'sketch-00/result/mv0/notation.log': 'The notation was written. The parts were checked against the score.'}}
        path = variants.collect(record)
        self.assertTrue(path)
        for e in path:
            node, keys = record, variants.steps(e['id'])
            for k in keys[:-1]:
                node = node[k]
            self.assertIn(keys[-1], node)


if __name__ == '__main__':
    unittest.main()
