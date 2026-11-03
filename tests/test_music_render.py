"""Structural diagnostics and safe reruns; no external renderer needed."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from music21 import meter, note, stream
from scheherazade.music.render import diagnostics, render


class RenderTests(unittest.TestCase):
    def test_wrong_bar_and_short_voice(self):
        score = stream.Score()
        part = stream.Part()
        measure = stream.Measure(number=1)
        measure.insert(0, meter.TimeSignature('3/4'))
        for length in (4, 2):
            voice = stream.Voice()
            voice.append(note.Note('C4', quarterLength=length))
            measure.insert(0, voice)
        part.append(measure)
        score.append(part)
        kinds = {w['kind'] for w in diagnostics(score)['warnings']}
        self.assertEqual(kinds, {'bar_length', 'voice_short'})

    def test_pickup_is_not_wrong_bar(self):
        score = stream.Score()
        part = stream.Part()
        measure = stream.Measure(number=0)
        measure.insert(0, meter.TimeSignature('3/4'))
        measure.append(note.Note('C4', quarterLength=1))
        measure.padAsAnacrusis()
        part.append(measure)
        score.append(part)
        self.assertEqual(diagnostics(score)['warnings'], [])

    def test_skip_only_complete_matching_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            abc = root / 'piece.abc'
            abc.write_text('X:1\nK:C\nC4|')
            abc.with_suffix('.json').write_text('{"prompt": ["Keyboard"]}')
            font = root / 'test.sf2'
            font.write_bytes(b'font')
            out = root / 'rendered'
            out.mkdir()
            (out / '.drafts').mkdir()
            digest = hashlib.sha256(abc.read_bytes() + abc.with_suffix('.json').read_bytes()).hexdigest()
            (out / 'piece.render.json').write_text(json.dumps({
                'source_sha256': digest, 'soundfont': str(font), 'renderer_version': 4}))
            for suffix in ('.abc', '.json', '.xml', '.pdf', '.mp3', '.mid', '.analysis.json'):
                (out / ('piece' + suffix)).write_text('complete')
            with patch('scheherazade.music.render.run', side_effect=RuntimeError('conversion started')) as run:
                render(abc, out, font, font)
                run.assert_not_called()
                (out / 'piece.mp3').write_bytes(b'')
                with self.assertRaisesRegex(RuntimeError, 'conversion started'):
                    render(abc, out, font, font)
                run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
