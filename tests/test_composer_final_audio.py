"""Final sound boundary; external engraving/audio tools are isolated here."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from mnemosyne.music import composer_worker as worker
from mnemosyne.music.composer import Night, Studio


class FinalAudioTests(unittest.TestCase):
    def test_compose_writes_notation_and_assignment_without_audio(self):
        from music21 import stream, note, instrument
        score = stream.Score()
        part = stream.Part()
        part.insert(0, instrument.Flute())
        part.append(note.Note('C4', quarterLength=4))
        score.insert(0, part)
        plan = {'school': 'fixture', 'seed': 1, 'audio_profile': 'native_sfz', 'tempo': 60}
        assignment = {'players': [{'id': 'flute', 'events': []}]}
        def engrave(s, base, log):
            s.write('musicxml', fp=base.with_suffix('.musicxml'))
            base.with_suffix('.ly').write_text('notation')
            base.with_suffix('.pdf').write_bytes(b'pdf')
        with tempfile.TemporaryDirectory() as tmp, \
             patch('mnemosyne.music.schools.SCHOOLS', {'fixture': Mock(compose=Mock(return_value=score))}), \
             patch('mnemosyne.music.orchestration.school_lines'), \
             patch('mnemosyne.music.orchestration.orchestrate', return_value=(score, assignment)), \
             patch('mnemosyne.music.orchestra_render.engrave', side_effect=engrave), \
             patch('mnemosyne.music.orchestra_render.render_orchestra', side_effect=AssertionError('audio')), \
             patch.object(worker, 'render_score', side_effect=AssertionError('audio')), \
             patch.object(worker.subprocess, 'check_output', return_value='Pages: 1'), \
             patch.object(worker, 'run'), patch.object(worker.analyze, 'features', return_value={}):
            out = Path(tmp)/'result'
            worker.execute({'action': 'compose', 'plan': plan}, out)
            self.assertEqual(json.loads((out/'rendered/orchestration.json').read_text()), assignment)
            self.assertTrue((out/'rendered/score.mid').is_file())
            self.assertTrue((out/'rendered/score.musicxml').is_file())
            self.assertFalse(any(p.suffix in ('.wav', '.mp3', '.flac', '.f32') for p in out.rglob('*')))
            self.assertFalse(list(out.rglob('.drafts')))

    def test_woven_symphony_uses_retained_movements_and_joins_lossless(self):
        plan = {'title': 'fixture', 'movements': [{}, {}, {}]}
        scores = [object(), object(), object()]
        movements = [{'xml': f'woven-{i}', 'plan': {'tempo': 60+i},
                      'assignment': {'fixture': i}} for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp, \
             patch('mnemosyne.music.symphony.validate'), \
             patch('mnemosyne.music.symphony.movement', side_effect=AssertionError('must not recompose')), \
             patch('mnemosyne.music.symphony.join_scores') as join, \
             patch('mnemosyne.music.symphony.write_score'), \
             patch('mnemosyne.weave.schools.performance_score', side_effect=scores) as performance, \
             patch('mnemosyne.music.orchestra_render.render_orchestra') as render, \
             patch.object(worker.subprocess, 'check_output', return_value='Pages: 1'), \
             patch.object(worker.subprocess, 'run'), \
             patch.object(worker, 'run') as commands, patch.object(worker.analyze, 'features', return_value={}):
            out = Path(tmp)/'result'
            worker.execute({'action': 'woven', 'form': 'symphony', 'plan': plan, 'movements': movements}, out)
            for i, call in enumerate(render.call_args_list):
                self.assertIs(call.args[0], scores[i])
                self.assertEqual(call.args[1:3], (movements[i]['plan'], movements[i]['assignment']))
                self.assertTrue(call.kwargs['compact'])
                self.assertEqual(performance.call_args_list[i].args[0].read_text(), f'woven-{i}')
            join.assert_called_once_with(scores, 'fixture')
            concat = next(c.args[0] for c in commands.call_args_list if '-filter_complex' in c.args[0])
            self.assertTrue(all(str(out/f'mv{i}/score.flac') in concat for i in range(3)))

    def test_night_sends_only_final_woven_movements_and_records_remote_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            woven = root/'woven'; woven.mkdir()
            carriers = []
            for i in range(3):
                folder = root/f'mv{i}'; folder.mkdir()
                (folder/'plan.json').write_text(json.dumps({'tempo': 60+i}))
                (folder/'orchestration.json').write_text(json.dumps({'player': i}))
                (folder/'score.musicxml').write_text('unwoven')
                (woven/f'final-mv{i+1}.musicxml').write_text(f'woven-{i}')
                carriers.append({'movement_index': i, 'score': f'mv{i}/score.musicxml'})
            night = Night.__new__(Night)
            night.root = root
            night.sound = True
            night.record = {'final': 'final', 'verdict': {'verdict': 'accept'}}
            final = {'id': 'final', 'stage': 'draft-02', 'form': 'symphony',
                     'plan': {'title': 'fixture'}, 'carriers': carriers[::-1]}
            night.sketches = [{'id': 'sketch'}, final]
            night.studio = Mock()
            remote = {'pod': 'studio-0', 'directory': '/work/composer/fixture/result'}
            night.studio.run.return_value = {'remote': remote}
            night.render_final(woven)
            night.studio.run.assert_called_once()
            request = night.studio.run.call_args.args[0]
            self.assertEqual([m['xml'] for m in request['movements']], ['woven-0', 'woven-1', 'woven-2'])
            self.assertEqual([m['assignment'] for m in request['movements']], [{'player': i} for i in range(3)])
            self.assertEqual(final['audio']['remote'], remote)
            self.assertEqual(night.record['sounding_work'], 'final')
            self.assertNotIn('audio', night.sketches[0])

    def test_sound_off_keeps_accepted_work_on_paper(self):
        with tempfile.TemporaryDirectory() as tmp:
            night = Night.__new__(Night)
            night.root = Path(tmp)
            night.studio = Mock()
            night.sound = False
            night.record = {'final': 'final', 'verdict': {'verdict': 'accept'}}
            night.render_final(night.root)
            night.studio.run.assert_not_called()
            self.assertTrue(night.record['sound'].startswith('off'))
            self.assertNotIn('sound_pending', night.record)

    def test_unfinished_never_renders_even_with_woven_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            night = Night.__new__(Night)
            night.root = Path(tmp)
            night.studio = Mock()
            night.record = {'status': 'unfinished', 'verdict': {'verdict': 'rewrite'}}
            night.render_final(night.root)
            night.studio.run.assert_not_called()
            self.assertEqual(night.record['status'], 'unfinished')

    def test_unfinished_backup_keeps_status_and_notation(self):
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from mnemosyne.atelier import obj
        with tempfile.TemporaryDirectory() as tmp:
            night = Night.__new__(Night)
            night.root = Path(tmp)
            night.studio = Mock()
            night.sketches = []
            night.objects = [obj('Notebook', 'unfinished', {'entries': ['retained']})]
            night.record = {'status': 'unfinished', 'verdict': {'verdict': 'rewrite'}}
            night.backup(X25519PrivateKey.generate())
            night.studio.run.assert_not_called()
            self.assertEqual(night.record['status'], 'unfinished')
            self.assertTrue((night.root/'pending-envelope.bin').exists())

    def test_imported_unpitched_percussion_does_not_require_program_change(self):
        from music21 import converter, instrument, note, stream
        from mnemosyne.music.schools.performance import write_midi
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = stream.Score()
            part = stream.Part()
            from mnemosyne.music.instrumentarium import notation_instrument
            ins = notation_instrument('cymbals')
            part.insert(0, ins); part.append(note.Unpitched())
            score.insert(0, part)
            from mnemosyne.music.symphony import write_score
            write_score(score, root/'score.musicxml')
            recovered = converter.parse(root/'score.musicxml')
            self.assertIsNone(recovered.parts[0].recurse().getElementsByClass('Instrument').first().midiProgram)
            write_midi(recovered, root/'score.mid', 60)
            self.assertTrue((root/'score.mid').read_bytes().startswith(b'MThd'))

    def test_cleanup_removes_only_attempt_audio(self):
        from mnemosyne.music.render import discard_audio_intermediates
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            attempt = root/'attempt'; attempt.mkdir()
            for ext in ('wav', 'flac', 'f32', 'mp3', 'json', 'log', 'musicxml'):
                (attempt/f'file.{ext}').write_text('fixture')
            (root/'score.flac').write_text('final')
            discard_audio_intermediates(attempt)
            self.assertEqual(sorted(p.suffix for p in attempt.iterdir()), ['.json', '.log', '.musicxml'])
            self.assertTrue((root/'score.flac').exists())
