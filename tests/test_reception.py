import copy
import json
import random
import unittest
from collections import Counter
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.lineage import Lineage
from mnemosyne.reception import Reception, ReviewWords
from mnemosyne.taste import make_taste, judge
from mnemosyne.weave import audience, catalogue, fountain, payload, DecodeError


class ReceptionTests(unittest.TestCase):
    def test_inner_errors_and_retained_drafts(self):
        taste, r = make_taste('a'), random.Random(7)
        self.assertTrue(any(judge(taste, .95, 1, r)[1] != 'accept' for _ in range(1000)))
        self.assertTrue(any(judge(taste, .15, 1, r)[1] == 'accept' for _ in range(1000)))
        life = Lineage('test', datetime(2025, 1, 1))
        for _ in range(40):
            w = life._work(life.artists[0])
            self.assertTrue(w['process']['drafts'])
        self.assertTrue(any(len(w['process']['drafts']) > 1 for w in life.artists[0].catalogue))
        self.assertEqual(len(life.artists[0].catalogue), 40)

    def test_reception_resume_and_words_do_not_change_fate(self):
        life = Lineage('test', datetime(2025, 1, 1))
        for _ in range(100):
            life.step({})
        other = Lineage.restore(json.loads(json.dumps(life.state())))
        for _ in range(30):
            life.step({}); other.step({})
        self.assertEqual(life.state(), other.state())
        before = life.reception.rng.getstate()
        class Writer:
            def __init__(self, nb): pass
            def ask(self, system, prompt, schema, step):
                assert 'private_merit' not in prompt + system
                return ReviewWords(text='An opinion.')
        life.reception.write_words(Writer)
        self.assertEqual(before, life.reception.rng.getstate())
        self.assertTrue(life.reception.reviews)
        self.assertTrue(all(not x['words_pending'] for x in life.reception.reviews))

    def test_reception_feeds_fame_and_money_even_after_death(self):
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        w = life._work(a, observation=dict(feature=[.5]*4, novelty=1, quality=.9, verdict='accept'))
        life.reception.register(a, w)
        a.status, a.recognition, a.wealth = 'dead', 0., 0.
        count = len(a.catalogue)
        life.night = 1
        life.reception.step(life)
        self.assertGreater(a.recognition, 0)
        self.assertGreater(a.wealth, 0)
        self.assertEqual(len(a.catalogue), count)

    def test_old_archive_import_preserves_works(self):
        life = Lineage('test', datetime(2025, 1, 1))
        work = life._work(life.artists[0])
        old = life.state()
        old['version'] = 1
        old.pop('reception')
        old['artists'][0].pop('inner_critic')
        restored = Lineage.restore(old)
        self.assertEqual(restored.artists[0].catalogue, [work])
        self.assertTrue(restored.artists[0].inner_critic)
        restored.step({})
        self.assertEqual(restored.state()['version'], 2)

    def test_notebook_edition_does_not_create_or_rewrite_work(self):
        life = Lineage('test', datetime(2025, 1, 1))
        a = life.artists[0]
        w = life._work(a, observation=dict(feature=[.5]*4, novelty=1, quality=.95, verdict='rewrite'))
        life._die(a, 'chance')
        life.reception.register(a, w)
        before = copy.deepcopy(a.catalogue)
        event = life.reception.release(w['id'], 400, 'from_notebooks', True)
        self.assertTrue(event['raw'] and event['posthumous'])
        self.assertEqual(a.catalogue, before)
        life.reception.review(w['id'], life.reception.critics[0], 400)
        self.assertEqual(life.reception.reviews[-1]['work'], w['id'])


class AudienceCarrierTests(unittest.TestCase):
    def test_roundtrip_loss_authentication_and_natural_statistics(self):
        key = X25519PrivateKey.from_private_bytes(bytes(range(32)))
        data = random.Random(3).randbytes(2200)
        enc = fountain.Encoder(payload.seal(data, key.public_key(), context=fountain.DOMAIN), 256, key)
        count = fountain.recommended_count(enc.total, 256)
        cat = catalogue.create(enc, [f'audience-{i}' for i in range(count)])
        decoded, bins, original_bins = [], Counter(), Counter()
        r = random.Random(8)
        for i in range(count):
            log = dict(id=f'audience-{i}', night=i, counts={'work': 256}, chart=['work'],
                       ratings={'work': .7}, programme=['work']*256,
                       timestamps_ms=[j*337000+r.randrange(256) for j in range(256)])
            original = copy.deepcopy(log)
            coded = audience.encode(log, enc.frame(i), key, cat, i)
            self.assertEqual(log, original)
            for k in ('counts', 'chart', 'ratings', 'programme'):
                self.assertEqual(log[k], coded[k])
            self.assertEqual([t//1000 for t in log['timestamps_ms']], [t//1000 for t in coded['timestamps_ms']])
            bins.update(t%1000 for t in coded['timestamps_ms'])
            original_bins.update(t%1000 for t in log['timestamps_ms'])
            decoded.append(audience.decode(coded, key))
            bad = copy.deepcopy(coded); bad['counts']['work'] += 1
            with self.assertRaises(DecodeError): audience.decode(bad, key)
            bad = copy.deepcopy(coded); bad['timestamps_ms'][0] ^= 1
            with self.assertRaises(DecodeError): audience.decode(bad, key)
        self.assertEqual(fountain.recover(decoded[count//4:], key), data)
        # A generous, fixed non-flaky chi-square bound (255 degrees of freedom).
        expected = count
        for observed in (bins, original_bins):
            chi = sum((observed[i]-expected)**2/expected for i in range(256))
            self.assertLess(chi, 360)
        self.assertEqual(audience.capacity({'timestamps_ms': []}), 0)
        self.assertEqual(enc.size, 168)

    def test_snapshot_api_and_empty_nights(self):
        key = X25519PrivateKey.generate()
        logs = [dict(id=f'n-{i}', night=i, counts={'w': 3}, chart=['w'], ratings={},
                     programme=['w']*256, timestamps_ms=[j*337000 for j in range(256)]) for i in range(60)]
        encoded = audience.pack(logs, b'cluster snapshot and notebooks', key)
        self.assertEqual(audience.recover(encoded[len(encoded)//4:], key), b'cluster snapshot and notebooks')
        with self.assertRaises(ValueError):
            audience.pack([dict(timestamps_ms=[])], b'data', key)
        with self.assertRaises(ValueError):
            audience.pack(logs[:1], b'data', key)
