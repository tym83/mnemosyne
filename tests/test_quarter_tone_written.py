"""A quarter tone on a transposing instrument survives the trip to written-pitch MusicXML."""
import tempfile
import unittest
from pathlib import Path

from music21 import converter, instrument, note, stream

from mnemosyne.music.orchestra_render import written
from mnemosyne.music.render import note_events


class QuarterToneTests(unittest.TestCase):
    def test_a_trumpet_quarter_sharp_comes_back_as_it_sounded(self):
        score, part = stream.Score(), stream.Part()
        part.insert(0, instrument.Trumpet())
        for ps in (71.5, 70.5, 72.0):
            n = note.Note(quarterLength=1)
            n.pitch.ps = ps
            part.append(n)
        score.insert(0, part)
        score.atSoundingPitch = part.atSoundingPitch = True
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp)/'s.musicxml'
            written(score).write('musicxml', fp=str(xml))
            back = converter.parse(xml).toSoundingPitch()
        self.assertEqual(note_events(score), note_events(back))


if __name__ == '__main__':
    unittest.main()
