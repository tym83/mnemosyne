"""LilyPond gets a score without the tempo steps that only sound."""
import tempfile
import unittest
from pathlib import Path

from music21 import meter, note, stream, tempo

from mnemosyne.music.orchestra_render import engravable


class EngravableTests(unittest.TestCase):
    def test_unshown_tempo_steps_leave_the_engraving_copy_only(self):
        part = stream.Part()
        part.insert(0, meter.TimeSignature('3/4'))
        part.insert(0, tempo.MetronomeMark(number=60))
        for k, bpm in enumerate((58, 56, 54)):
            step = tempo.MetronomeMark(number=bpm)
            step.numberImplicit = True
            part.insert(3 * (k + 1), step)
        for _ in range(4):
            part.append(note.Note('C4', quarterLength=3))
        score = stream.Score([part])
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp)/'score.musicxml'
            score.write('musicxml', fp=str(xml))
            copy = engravable(xml)
            self.assertIn('tempo="58"', xml.read_text())
            text = copy.read_text()
            self.assertNotIn('<words />', text)
            self.assertNotIn('tempo="58"', text)
            self.assertIn('<per-minute>60</per-minute>', text)
            self.assertEqual(text.count('<note'), xml.read_text().count('<note'))
