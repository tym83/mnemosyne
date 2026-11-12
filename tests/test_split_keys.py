"""The owner reads, the atelier writes: the owner's private key never enters the cluster."""
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.operator.keys import load
from mnemosyne.restore import recover_works
from mnemosyne.weave import fountain, payload
from mnemosyne.weave.keys import ReadingKey, WritingKey


class SplitKeyTests(unittest.TestCase):
    def test_atelier_seals_what_it_cannot_open(self):
        owner, atelier = X25519PrivateKey.generate(), X25519PrivateKey.generate()
        writing = WritingKey(atelier, owner.public_key())
        reading = ReadingKey(owner, atelier.public_key())
        self.assertEqual(writing.private_bytes_raw(), reading.private_bytes_raw())
        envelope = payload.seal(b'state', writing.public_key(), context=fountain.DOMAIN)
        self.assertEqual(payload.open_envelope(envelope, reading, context=fountain.DOMAIN), b'state')
        with self.assertRaises(PermissionError):
            payload.open_envelope(envelope, writing, context=fountain.DOMAIN)
        stranger = ReadingKey(X25519PrivateKey.generate(), atelier.public_key())
        self.assertNotEqual(stranger.private_bytes_raw(), writing.private_bytes_raw())

    def test_cluster_key_config_holds_only_the_owner_public_key(self):
        owner, atelier = X25519PrivateKey.generate(), X25519PrivateKey.generate()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'atelier.key'
            path.write_bytes(atelier.private_bytes_raw())
            key = load({'provider': 'file', 'path': str(path),
                        'ownerPublic': owner.public_key().public_bytes_raw().hex()})
            self.assertIsInstance(key, WritingKey)
            with self.assertRaises(ValueError):
                load({'provider': 'file', 'path': str(path)})

    def test_owner_restores_works_written_with_split_keys(self):
        from tests.test_composer_transport import cluster, night
        owner, atelier = X25519PrivateKey.generate(), X25519PrivateKey.generate()
        writing = WritingKey(atelier, owner.public_key())
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            n = night(tmp/'n', cluster(), tmp/'ledger', '2025-07-01T00:00:00')
            n.backup(writing)
            woven = next((tmp/'n/woven').glob('*.musicxml'))
            self.assertIn(writing.atelier_public(), woven.read_text())
            _, objects, _ = recover_works(tmp/'n/woven', owner)
            self.assertEqual({o['kind'] for o in objects}, {'Namespace', 'ConfigMap', 'Deployment'})
            with self.assertRaises(ValueError):
                recover_works(tmp/'n/woven', X25519PrivateKey.generate())


if __name__ == '__main__':
    unittest.main()
