from copy import deepcopy
import hashlib
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from scheherazade.weave import DecodeError, backup, catalogue, fountain, payload


class FountainTests(unittest.TestCase):
    def setUp(self):
        self.key = X25519PrivateKey.generate()
        self.data = random.Random(42).randbytes(12000)
        self.envelope = payload.seal(self.data, self.key.public_key(), context=fountain.DOMAIN)
        self.encoder = fountain.Encoder(self.envelope, 256, self.key)

    def test_thirty_percent_loss_many_seeds_and_repair_only(self):
        n = fountain.recommended_count(len(self.envelope), 256)
        frames = [self.encoder.frame(i) for i in range(n)]
        for seed in range(40):
            survivors = random.Random(seed).sample(frames, n - n * 30 // 100)
            self.assertEqual(fountain.recover(survivors, self.key), self.data)
        repairs = [self.encoder.frame(i) for i in range(100000, 100000 + self.encoder.k + 32)]
        self.assertEqual(fountain.reconstruct(repairs, self.key), self.envelope)

    def test_systematic_and_duplicate_frames(self):
        frames = [self.encoder.frame(i) for i in range(self.encoder.k)]
        self.assertEqual(fountain.recover(frames + frames, self.key), self.data)
        for incomplete in ([], frames[:-1], [frames[0]] * self.encoder.k):
            with self.assertRaises(DecodeError):
                fountain.recover(incomplete, self.key)

    def test_authentication_mixed_snapshots_and_dimensions(self):
        frame = self.encoder.frame(0)
        for index in range(len(frame)):
            changed = bytearray(frame)
            changed[index] ^= 1
            with self.assertRaises(DecodeError):
                fountain.unpack(bytes(changed), self.key)
        with self.assertRaises(DecodeError):
            fountain.unpack(frame, X25519PrivateKey.generate())
        other = payload.seal(self.data, self.key.public_key(), context=fountain.DOMAIN)
        for encoder in (fountain.Encoder(other, 256, self.key),
                        fountain.Encoder(self.envelope, 512, self.key)):
            with self.assertRaises(DecodeError):
                fountain.recover([frame, encoder.frame(1)], self.key)
        for truncated in (frame[:10], frame[:-1]):
            with self.assertRaises(DecodeError):
                fountain.unpack(truncated, self.key)

    def test_bounds(self):
        for capacity in (0, fountain.OVERHEAD, fountain.MAX_CAPACITY + 1):
            with self.assertRaises(ValueError):
                fountain.Encoder(self.envelope, capacity, self.key)
        for index in (-1, 2**64):
            with self.assertRaises(ValueError):
                self.encoder.frame(index)

    def test_catalogue_replicated_and_authenticated(self):
        cat = catalogue.create(self.encoder, ['painting', 'music'])
        a = catalogue.metadata(cat, 0, {'idea': 'unchanged'})
        b = catalogue.metadata(cat, 1)
        self.assertEqual(a['backup']['catalogue'], b['backup']['catalogue'])
        self.assertEqual(a['idea'], 'unchanged')
        catalogue.validate_work(self.encoder.frame(0), a, self.key)
        with self.assertRaises(DecodeError):
            catalogue.validate_work(self.encoder.frame(1), a, self.key)
        changed = deepcopy(a)
        changed['backup']['catalogue']['body']['works'][0] = 'substitution'
        with self.assertRaises(DecodeError):
            catalogue.validate_work(self.encoder.frame(0), changed, self.key)
        with self.assertRaises(ValueError):
            catalogue.create(self.encoder, ['same', 'same'])

    def test_packages_survive_without_external_catalogue_or_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'bundle'
            with patch.object(payload, 'seal', wraps=payload.seal) as seal:
                cat = backup.package(self.data, root, self.key, 512)
                self.assertEqual(seal.call_count, 1)
            works = sorted(p for p in root.iterdir() if p.is_dir())
            survivors = random.Random(7).sample(works, len(works) - len(works) * 30 // 100)
            self.assertEqual(backup.recover(survivors, self.key), self.data)
            self.assertEqual(hashlib.sha256((root / 'envelope.bin').read_bytes()).hexdigest(),
                             cat['body']['snapshot'])
