"""Lives, reviews, notebooks and the audience panel carry the night's frames."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.lineage import Lineage
from mnemosyne.restore import recover_works
from mnemosyne.weave import audience, fountain, payload
from mnemosyne.weave import night as tonight
from mnemosyne.weave.keys import WritingKey
from tests.test_composer_transport import cluster
from tests.test_variants import draft


def lived(nights=40, seed=4):
    life = Lineage('leonia', datetime(2025, 1, 1), seed=seed)
    for _ in range(nights):
        life.step({})
    return life


class PanelTests(unittest.TestCase):
    def test_frame_round_trips_and_keeps_other_sessions(self):
        life = lived()
        log = next(l for l in life.reception.logs if audience.frame_capacity(l) >= 192)
        key = X25519PrivateKey.generate()
        encoder = fountain.Encoder(payload.seal(b'x' * 300, key.public_key(), context=fountain.DOMAIN), 192, key)
        from mnemosyne.weave import catalogue
        cat = catalogue.create(encoder, ['w'])
        woven = audience.encode_frame(log, encoder.frame(0), key, [catalogue.metadata(cat, 0)])
        self.assertEqual(audience.decode_frame(woven, key), encoder.frame(0))
        self.assertEqual([t // 1000 for t in woven['timestamps_ms']], [t // 1000 for t in log['timestamps_ms']])
        self.assertEqual(woven['timestamps_ms'][200:], log['timestamps_ms'][200:])


class TextsTests(unittest.TestCase):
    def test_unwoven_drafts_are_gathered_once_and_published(self):
        life = lived()
        review = life.reception.reviews[0]
        review['text'] = 'Вещь {тихая|робкая} и {честная|прямая}.'
        aid = next(iter(life.biographies))
        life.biographies[aid].chapters[0]['text'] = 'Он {родился|явился} в {мае|марте}.'
        record = {'entries': [{'result': {'diary': 'Я {шёл|брёл}.'}}]}
        entries, publish = tonight.texts(life, [('w1', record)])
        ids = {e['id'] for e in entries}
        # The author's variants are gathered, and every other unwoven prose text is typeset too.
        self.assertIn('/notebooks/w1/entries/0/result/diary', ids)
        self.assertIn(f'/reviews/{review["id"]}', ids)
        self.assertGreaterEqual(len(entries), 3)
        from mnemosyne.weave import variants
        publish({'entries': variants.realize(entries, [0] * len(variants.radices(entries)))})
        self.assertTrue(review['woven'])
        self.assertEqual(review['apparatus'], 'Вещь {тихая|робкая} и {честная|прямая}.')
        self.assertEqual(review['text'], 'Вещь тихая и честная.')
        self.assertIn('/entries/0/result/diary', record['apparatus'])
        self.assertEqual(tonight.texts(life, [])[0], [])


class OperatorNightTests(unittest.TestCase):
    def test_lives_and_reviews_carry_and_restore_with_split_keys(self):
        from mnemosyne.operator.worker import weave
        life = lived()
        for i, review in enumerate(life.reception.reviews[:3]):
            review['text'] = draft(900, seed=i)
        owner, atelier = X25519PrivateKey.generate(), X25519PrivateKey.generate()
        key = WritingKey(atelier, owner.public_key())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'night'
            root.mkdir()
            entries, publish = tonight.texts(life)
            report = weave(cluster(), [], root, key, extra=[('texts', entries, 'variants', publish)],
                           at='2025-07-01T00:00:00')
            self.assertIn('texts', report['carriers'])
            self.assertTrue(all(r.get('woven') for r in life.reception.reviews[:3]))
            self.assertNotIn('{', life.reception.reviews[0]['text'])
            if not report['pending_pieces']:
                _, objects, _ = recover_works(root/'woven', owner)
                self.assertIn('ConfigMap', {o['kind'] for o in objects})


if __name__ == '__main__':
    unittest.main()
