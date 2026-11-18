"""A school piece whose length is not a whole number of bars keeps its rest-completed last bar."""
import unittest

from music21 import meter, note, stream

from mnemosyne.music.schools.common import fits


def part(notes_quarters, rest_quarters):
    p = stream.Part()
    p.insert(0, meter.TimeSignature('4/4'))
    p.append(note.Note('C4', quarterLength=notes_quarters))
    if rest_quarters:
        p.append(note.Rest(quarterLength=rest_quarters))
    return p


class FinalBarTests(unittest.TestCase):
    def test_a_last_bar_completed_with_rest_fits(self):
        self.assertTrue(fits(part(6, 2), 6))

    def test_exact_length_fits(self):
        self.assertTrue(fits(part(8, 0), 8))

    def test_notes_past_the_plan_do_not_fit(self):
        self.assertFalse(fits(part(8, 0), 6))

    def test_a_whole_extra_bar_does_not_fit(self):
        self.assertFalse(fits(part(4, 4), 4))


if __name__ == '__main__':
    unittest.main()
