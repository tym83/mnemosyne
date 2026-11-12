import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mnemosyne.lineage import Lineage
from mnemosyne.music.composer import Method, Night, Studio, validate_plan, plan_contract
from mnemosyne.restore import read_archive
from mnemosyne.state.collect import archive


class ComposerTests(unittest.TestCase):
    def test_unrenderable_orchestras_rejected_before_worker(self):
        from mnemosyne.music.symphony import test_plan
        method = self.method().model_copy(update={'form': 'symphony'})
        for orchestra, message in [([{'instrument': 'voice', 'type': 'alto'}], 'Unknown instrument'),
                                   ([{'instrument': 'alto'}], 'unavailable for audio'),
                                   ([{'instrument': 'flute'}], 'default orchestra slots')]:
            plan = test_plan()
            plan['orchestra'] = orchestra
            with self.subTest(orchestra=orchestra), self.assertRaisesRegex(ValueError, message):
                validate_plan(plan, method, sketch=True)
        contract = plan_contract(method)
        self.assertIn('alto', contract['audio']['unavailable'])
        self.assertNotIn('alto', contract['audio']['instruments'])

    def test_artist_receives_constraints_and_exhausted_plans_are_retained(self):
        from mnemosyne.music.composer import PlanText
        from mnemosyne.music.symphony import test_plan
        from mnemosyne.artist import Statement
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        method = self.method().model_copy(update={'form': 'symphony'})
        plan = test_plan()
        plan['orchestra'] = [{'instrument': 'alto'}]
        st = Statement(**{k: [] if f.annotation == list[str] else 'fixture'
                         for k, f in Statement.model_fields.items()})
        prompts = []
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import Mock
            studio = Mock(spec=['run'])
            night = Night(life, life.artists[0].id, Path(tmp)/'work', studio)
            def ask(system, prompt, schema, step, **kwargs):
                if schema is Method:
                    return method
                prompts.append(prompt)
                return PlanText(plan_json=json.dumps(plan), diary='retained choice')
            with patch('mnemosyne.artist.statement', return_value=(st, [{'interrogation': {'verdict': 'accept'}}])), \
                 patch('mnemosyne.artist.halftones') as shades, \
                 patch.object(night, 'ask', side_effect=ask):
                shades.return_value.model_dump.return_value = {}
                result = night.run('quiet')
            self.assertEqual(result['status'], 'plan_rejected')
            self.assertEqual(len(prompts), 3)
            self.assertIn('unavailable for audio', prompts[1])
            self.assertEqual(sum('invalid_plan' in e for e in result['entries']), 3)
            studio.run.assert_not_called()
            self.assertFalse(life.artists[0].catalogue)

    def test_worker_stderr_is_in_archived_failed_notebook(self):
        class FailedStudio:
            def run(self, request, destination):
                destination.mkdir()
                (destination/'studio.log').write_text('Traceback: rendering failed\n')
                raise RuntimeError('worker exited 1')
        life = Lineage('test', datetime(2025, 1, 1))
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, life.artists[0].id, Path(tmp)/'work', FailedStudio())
            with self.assertRaisesRegex(RuntimeError, 'worker exited 1'):
                night.music({'title': 'fixture'}, self.method(), 'sketch-00')
            objects = read_archive(archive(night.objects))
            notebook = next(o for o in objects if o['kind'] == 'Notebook'
                            and o['metadata']['name'] == night.work_id+'-notebook')
            self.assertIn('Traceback', notebook['spec']['entries'][-1]['worker_logs']['sketch-00/studio.log'])

    def test_worker_keeps_traceback_without_mutating_previous_result(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = root/'request.json'
            request.write_text(json.dumps({'action': 'compose', 'form': 'symphony',
                                          'plan': {'orchestra': [{'instrument': 'voice'}]}}))
            out = root/'result'
            command = [sys.executable, '-m', 'mnemosyne.music.composer_worker',
                       str(request), '--out', str(out)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 1)
            trace = (out/'stderr.log').read_text()
            self.assertIn('Unknown instrument', trace)
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(again.returncode, 1)
            self.assertIn('FileExistsError', again.stderr)
            self.assertEqual((out/'stderr.log').read_text(), trace)

    def method(self):
        return Method(kind='school', school='tintinnabuli', sources=['tintinnabuli'],
                      principle='triad', transformation='', concept='test', reason='test',
                      notagen_prompt='', form='school')

    def test_plans_are_validated_without_composing(self):
        plan = json.loads(Path('src/mnemosyne/music/schools/plans/tintinnabuli.json').read_text())
        self.assertEqual(validate_plan(plan, self.method()), plan)
        plan['duration'] += 1
        with self.assertRaises(ValueError):
            validate_plan(plan, self.method())
        plan['school'] = 'unknown'
        with self.assertRaises(ValueError):
            validate_plan(plan, self.method())

    def test_only_living_workers_and_authorized_studios(self):
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        with tempfile.TemporaryDirectory() as tmp:
            for status in ('silent', 'dead'):
                life.artists[0].status = status
                with self.assertRaises(ValueError):
                    Night(life, life.artists[0].id, Path(tmp)/status, None)
            with self.assertRaises(ValueError):
                Studio(Path(tmp), 'studio-2')

    def test_pending_notebook_and_biography_survive_archive(self):
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, life.artists[0].id, Path(tmp)/'work', None)
            night.entries.append({'step': 'method', 'error': 'retained failed choice'})
            night.save()
            objects = read_archive(archive(night.objects))
            notebook = next(o for o in objects if o['kind'] == 'Notebook'
                            and o['metadata']['name'] == night.work_id+'-notebook')
            self.assertEqual(notebook['spec']['entries'][0]['error'], 'retained failed choice')
            restored = Lineage.from_objects(objects, 'test')
            self.assertEqual(restored.state(), life.state())
            with self.assertRaises(FileExistsError):
                Night(life, life.artists[0].id, Path(tmp)/'work', None)

    def test_failed_writer_is_checkpointed(self):
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, life.artists[0].id, Path(tmp)/'work', None)
            with patch('mnemosyne.artist.statement', side_effect=RuntimeError('writer unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'writer unavailable'):
                    night.run('quiet')
            self.assertEqual(json.loads((night.root/'notebook.json').read_text())['status'], 'failed')
            self.assertFalse(life.artists[0].catalogue)

    def test_rejected_idea_cannot_compose(self):
        from mnemosyne.artist import Statement
        st = Statement(**{k: [] if f.annotation == list[str] else 'idea'
                          for k, f in Statement.model_fields.items()})
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, life.artists[0].id, Path(tmp)/'work', None)
            with patch('mnemosyne.artist.statement', return_value=(st, [{'interrogation': {'verdict': 'rewrite'}}])):
                result = night.run('quiet')
            self.assertEqual(result['status'], 'idea_rejected')
            self.assertFalse(life.artists[0].catalogue)
            a = life.artists[0]
            self.assertEqual(a.problem, 'idea')
            self.assertEqual(a.rejections, 1)
            self.assertGreater(a.despair, 0)
            self.assertEqual(a.notebook[-1]['kind'], 'set_aside')

    def test_set_aside_idea_returns_next_night_and_accept_clears_it(self):
        from mnemosyne.artist import Statement
        st = Statement(**{k: [] if f.annotation == list[str] else 'idea'
                          for k, f in Statement.model_fields.items()})
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        a.portrait, a.problem = 'Fixture portrait', 'old idea'
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, a.id, Path(tmp)/'work', None)
            seen = {}
            def statement(*args, **kw):
                seen.update(kw)
                raise RuntimeError('stop after the idea stage')
            with patch('mnemosyne.artist.statement', side_effect=statement):
                with self.assertRaises(RuntimeError):
                    night.run('quiet')
            self.assertEqual(seen['set_aside'], 'old idea')
            self.assertNotIn('interrogator', seen)

    def test_free_text_accept_verdict_is_accepted(self):
        from mnemosyne.artist import accepted
        self.assertTrue(accepted('ACCEPT. The form breathes.'))
        self.assertFalse(accepted('REWRITE. Allegory of one thought.'))

    def test_completed_night_keeps_images_corrections_and_real_work(self):
        from mnemosyne.artist import Statement, Halftones, Shade
        from mnemosyne.music.composer import PlanText, Listening, Chapter
        from mnemosyne.atelier import Atelier
        st = Statement(**{k: [] if f.annotation == list[str] else 'fixture idea'
                          for k, f in Statement.model_fields.items()})
        shade = Shade(shade='fixture', why_mine='fixture', how_it_shows='fixture')
        tones = Halftones(thought=shade, embodiment=shade, nuances=[], overall='fixture')
        plan = json.loads(Path('src/mnemosyne/music/schools/plans/tintinnabuli.json').read_text())
        class FixtureStudio:
            def run(self, request, destination):
                folder = destination/'result'
                folder.mkdir(parents=True)
                for name in ('score.musicxml', 'page.png', 'score.mp3'):
                    (folder/name).write_text('test double; not a composition')
                return {'score': 'score.musicxml', 'images': ['page.png'],
                        'analysis': {'bpm': 48, 'density': [2], 'parts': 2, 'reprise': 0}}
        calls = []
        def ask(system, prompt, schema, step, **kwargs):
            calls.append((step, kwargs.get('images')))
            if schema is PlanText:
                return PlanText(plan_json=json.dumps(plan), diary='fixture plan')
            if schema is Method:
                return self.method()
            if schema is Chapter:
                return Chapter(text='Fixture chronicle chapter')
            if schema is Listening:
                return Listening(verdict='rewrite' if step.endswith(':0') else 'accept',
                                 reasons='fixture', corrections=['fixture correction'], matters=True, quality=.8)
            raise AssertionError(schema)
        life = Lineage('test', datetime(2025, 1, 1))
        life.artists[0].portrait = 'Fixture portrait'
        with tempfile.TemporaryDirectory() as tmp:
            night = Night(life, life.artists[0].id, Path(tmp)/'work', FixtureStudio())
            with patch('mnemosyne.artist.statement', return_value=(st, [{'interrogation': {'verdict': 'accept'}}])), \
                 patch('mnemosyne.artist.halftones', return_value=tones), \
                 patch.object(night.writer, 'ask', side_effect=ask):
                result = night.run('quiet', drafts=3)
            self.assertEqual(result['status'], 'accepted')
            self.assertEqual(len(result['sketches']), 3)
            self.assertTrue(all(images for step, images in calls if step.startswith('listen:')))
            work = life.artists[0].catalogue[-1]
            self.assertFalse(work['synthetic'])
            self.assertEqual(work['idea'], st.idea)
            self.assertEqual(life.biographies[life.artists[0].id].chapters[-1]['text'], 'Fixture chronicle chapter')
            objects = read_archive(archive(night.objects))
            restored = Lineage.from_objects(objects, 'test')
            atelier = Atelier('test', Path(tmp)/'again')
            atelier.lineage(restored)
            for sketch in result['sketches']:
                retained = next(o for o in atelier.objects if o['kind'] == 'Sketch' and o['metadata']['name'] == sketch['id'])
                self.assertTrue(retained['spec']['files'])
            # Object identities remain unique when both generic and night exports run.
            self.assertEqual(len(objects), len({(o['kind'], o['metadata']['name']) for o in objects}))

    def test_two_year_mortality_clock(self):
        from mnemosyne.lineage import Parameters
        p = Parameters()
        survival = 1.
        for day in range(1, 731):
            survival *= 1-p.accident-p.age_hazard*max(0, (day-p.old_age)/365)
        self.assertAlmostEqual(survival, .5, delta=.04)
        self.assertLess(p.maturity, p.late_age)
        self.assertLess(p.late_age, p.old_age)
        self.assertEqual((p.onset_nights, p.crisis_nights, p.recovery_nights), (4, 8, 12))


if __name__ == '__main__':
    unittest.main()
