"""A composer sees the forms and ensembles of their own latest works before choosing the next."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest

from mnemosyne.music.composer import Night


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


if __name__ == '__main__':
    unittest.main()
