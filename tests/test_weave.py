import os
import unittest

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from scheherazade.weave import DecodeError
from scheherazade.weave import arithmetic, payload


class ArithmeticTests(unittest.TestCase):
    def test_all_byte_values_nonbinary_and_tight_capacity(self):
        for radices in ([257], [3] * 6, [2] * 8, [5, 7, 11]):
            for value in range(256):
                data = bytes([value])
                self.assertEqual(arithmetic.decode(arithmetic.encode(data, radices), radices, 1), data)

    def test_variable_slots_leading_zeroes(self):
        data = b'\x00\x00' + os.urandom(100)
        radices = [3, 5, 7] * 130
        self.assertEqual(arithmetic.decode(arithmetic.encode(data, radices), radices, len(data)), data)

    def test_invalid_channel(self):
        with self.assertRaises(ValueError):
            arithmetic.encode(b'x', [2] * 7)
        for digits, radices, size in [([2], [2], 0), ([], [2], 0), ([0], [2], 1), ([1], [3], 0)]:
            with self.assertRaises(DecodeError):
                arithmetic.decode(digits, radices, size)


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.key = X25519PrivateKey.generate()
        self.data = b'cluster state\x00' * 100
        self.frame = payload.seal(self.data, self.key.public_key(), context=b'work')

    def test_round_trip_and_randomization(self):
        self.assertEqual(payload.open_envelope(self.frame, self.key, context=b'work'), self.data)
        self.assertNotEqual(self.frame, payload.seal(self.data, self.key.public_key(), context=b'work'))

    def test_every_byte_tamper_and_truncation(self):
        for i in range(len(self.frame)):
            changed = bytearray(self.frame)
            changed[i] ^= 1
            with self.assertRaises(DecodeError):
                payload.open_envelope(bytes(changed), self.key, context=b'work')
            with self.assertRaises(DecodeError):
                payload.open_envelope(self.frame[:i], self.key, context=b'work')

    def test_wrong_key_and_work(self):
        for key, context in [(X25519PrivateKey.generate(), b'work'), (self.key, b'changed note')]:
            with self.assertRaises(DecodeError):
                payload.open_envelope(self.frame, key, context=context)

    def test_forged_checksum_still_fails_authentication(self):
        import struct
        import zlib
        body = bytearray(self.frame[:-4])
        body[-1] ^= 1
        frame = bytes(body) + struct.pack('>I', zlib.crc32(body))
        with self.assertRaises(DecodeError):
            payload.open_envelope(frame, self.key, context=b'work')

    def test_arithmetic_transport(self):
        radices = [3, 5] * (len(self.frame) * 3)
        recovered = arithmetic.decode(arithmetic.encode(self.frame, radices), radices, len(self.frame))
        self.assertEqual(payload.open_envelope(recovered, self.key, context=b'work'), self.data)


class MusicDiagnosticsTests(unittest.TestCase):
    def test_parallel_outer_voices_and_crossing(self):
        from music21 import note, stream
        from scheherazade.weave.music import style_check
        score = stream.Score()
        upper, lower = stream.Part(), stream.Part()
        for name in ('G4', 'A4'):
            upper.append(note.Note(name))
        for name in ('C4', 'D4'):
            lower.append(note.Note(name))
        score.insert(0, upper)
        score.insert(0, lower)
        result = style_check(score)
        self.assertEqual(result['outer_parallel_fifths'], 1)
        self.assertEqual(result['staff_crossing_onsets'], 0)
        lower.notes[0].pitch.nameWithOctave = 'C5'
        self.assertEqual(style_check(score)['staff_crossing_onsets'], 1)


if __name__ == '__main__':
    unittest.main()
