"""A new school is born only through its own grammar, trial and inner critic."""
import json
import unittest
from datetime import datetime
from pathlib import Path

from mnemosyne.artist import Judgement
from mnemosyne.lineage import Lineage
from mnemosyne.music import school_birth
from mnemosyne.music.school_birth import GrammarText, check, found, school_id, trial

BREATH = Path(__file__).parent/'fixtures/born_breath.py'


def forget_born():
    from mnemosyne.music.schools import SCHOOLS
    for name in [n for n, m in SCHOOLS.items() if hasattr(m, '__source__')]:
        del SCHOOLS[name]


def tearDownModule():
    forget_born()


def plan_for(name):
    plan = json.loads(Path('src/mnemosyne/music/schools/plans/drone.json').read_text())
    plan.update(school=name, title=name)
    return plan


class AdmissionTests(unittest.TestCase):
    def test_unsafe_code_is_refused_before_it_runs(self):
        for code in ('import os', 'from subprocess import run', 'open("x")', 'x = (1).__class__',
                     'getattr(1, "real")', 'class A: pass', 'eval("1")', 'from ..weave import payload'):
            self.assertTrue(check(code + '\ndef compose(plan, seed, *, choices=None): pass\nFREE_CHANNELS = {}'), code)
        self.assertEqual(check(BREATH.read_text()), [])

    def test_trial_admits_a_distinct_grammar(self):
        name = school_id('Школа дыхания')
        report = trial(name, BREATH.read_text(), plan_for(name))
        self.assertEqual(report['errors'], [])
        self.assertTrue(report['distinct'])
        self.assertGreaterEqual(report['bytes_per_3_min'], school_birth.MIN_BYTES_PER_3_MIN)

    def test_renamed_founding_school_is_not_a_new_school(self):
        source = Path('src/mnemosyne/music/schools/drone.py').read_text()
        report = trial('born-clone-000000', source, plan_for('born-clone-000000'))
        self.assertEqual(report['errors'], [])
        self.assertFalse(report['distinct'])
        self.assertEqual(report['nearest']['school'], 'drone')

    def test_broken_grammar_reports_instead_of_crashing(self):
        report = trial('born-broken-000000', 'def compose(plan, seed, *, choices=None):\n    return 1/0\n'
                       'FREE_CHANNELS = {"period_quarters": 0.5, "levels": 16, "step_percent": 0.25, '
                       '"max_deviation_percent": 1.875}', plan_for('born-broken-000000'))
        self.assertTrue(any('ZeroDivisionError' in e for e in report['errors']))


class FoundingTests(unittest.TestCase):
    def ask_with(self, grammars, verdict='accept'):
        calls = []
        def ask(system, prompt, schema, step, **kw):
            calls.append(step)
            if schema is GrammarText:
                source = grammars.pop(0)
                name = school_id('Школа дыхания')
                return GrammarText(source=source, plan_json=json.dumps(plan_for(name)), diary='d')
            return Judgement(verdict=verdict, is_reinvention_of='', coherent='c', generative='g', objections=['o'])
        return ask, calls

    def test_artist_revises_until_the_trial_passes(self):
        ask, calls = self.ask_with(['def compose(:', BREATH.read_text()])
        record, history = found({'name': 'Школа дыхания', 'manifesto': ['m']}, ask, 'artist', 'critic')
        self.assertEqual(record['status'], 'accepted')
        self.assertEqual(calls, ['school-grammar:0', 'school-grammar:1', 'school-judgement:1'])
        self.assertTrue(history[0]['trial']['errors'])

    def test_inner_critic_can_refuse_a_valid_school(self):
        ask, _ = self.ask_with([BREATH.read_text()] * 3, verdict='rewrite')
        record, history = found({'name': 'Школа дыхания', 'manifesto': ['m']}, ask, 'artist', 'critic')
        self.assertIsNone(record)
        self.assertEqual(len(history), 3)


def born_record():
    name = school_id('Школа дыхания')
    return {'id': name, 'name': 'Школа дыхания', 'manifesto': {'manifesto': ['m']},
            'source': BREATH.read_text(), 'plan': plan_for(name)}


class LineageTests(unittest.TestCase):
    def tearDown(self):
        forget_born()

    def test_founded_school_survives_restore_and_composes_after_it(self):
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        record = life.found_school(a.id, born_record())
        self.assertEqual(a.school, record['id'])
        restored = Lineage.restore(json.loads(json.dumps(life.state())))
        self.assertEqual(restored.schools[record['id']]['author'], a.id)
        school_birth.register_all(restored.schools)
        from mnemosyne.music.schools import SCHOOLS
        self.assertTrue(SCHOOLS[record['id']].compose(record['plan'], 7).parts)

    def test_school_spreads_by_borrowed_method_and_apprenticeship(self):
        from mnemosyne.lineage import Parameters
        life = Lineage('test', datetime(2025, 1, 1), seed=5, parameters=Parameters(arts=('music',)))
        founder = life.artists[0]
        record = life.found_school(founder.id, born_record())
        for b in life.artists[1:]:
            b.openness, b.isolation, b.solitude = 1., 0., 0.
        founder.isolation = founder.solitude = 0.
        for _ in range(3000):
            life.step({})
            if record['followers']:
                break
        self.assertTrue(record['followers'] or any(a.school == record['id'] for a in life.artists[1:]))

    def test_unborn_school_is_kept_and_hurts(self):
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        life.school_unborn(a.id, 'Школа', [{'round': 0}])
        self.assertEqual(a.notebook[-1]['kind'], 'school_unborn')
        self.assertGreater(a.despair, 0)


if __name__ == '__main__':
    unittest.main()


class ComposerFoundingTests(unittest.TestCase):
    def tearDown(self):
        forget_born()
    def night(self, tmp):
        from mnemosyne.music.composer import Night
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        night = Night(life, life.artists[0].id, Path(tmp)/'work', None)
        night.system = 'artist'
        return night

    def manifesto(self, *args, **kw):
        from mnemosyne.artist import Method
        return Method(choice='invent', kind_of_creativity='t', name='Школа дыхания', based_on=[], broken_principles=[],
                      manifesto=['m'], philosophy='p', techniques=[], forbids=[], rejects_and_argues_with='r',
                      why_this_serves_the_idea='w', works_it_could_make=[])

    def test_born_school_becomes_the_method_and_travels_to_the_studio(self):
        import tempfile
        from unittest.mock import patch
        record = born_record()
        with tempfile.TemporaryDirectory() as tmp:
            night = self.night(tmp)
            with patch.object(night.writer, 'ask', side_effect=self.manifesto), \
                 patch('mnemosyne.music.school_birth.found', return_value=(record, [{'round': 0}])):
                stub = type('S', (), {'model_dump': lambda self: {}})()
                school = night.found_school(stub, stub)
            self.assertEqual(school, record['id'])
            self.assertEqual(night.artist.school, school)
            self.assertIn(school, night.born_sources())
            from mnemosyne.music.composer import example_plan, plan_contract, Method
            self.assertEqual(example_plan(school)['school'], school)
            m = Method(kind='school', school=school, sources=[], principle='', transformation='', concept='',
                       reason='', notagen_prompt='', form='school')
            self.assertEqual(plan_contract(m)['grammar'], record['source'])

    def test_unborn_school_ends_the_night_in_the_notebook(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            night = self.night(tmp)
            with patch.object(night.writer, 'ask', side_effect=self.manifesto), \
                 patch('mnemosyne.music.school_birth.found', return_value=(None, [{'round': 0}])):
                stub = type('S', (), {'model_dump': lambda self: {}})()
                self.assertIsNone(night.found_school(stub, stub))
            self.assertEqual(night.record['status'], 'school_unborn')
            self.assertEqual(night.artist.notebook[-1]['kind'], 'school_unborn')
