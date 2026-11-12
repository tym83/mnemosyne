"""The author's own variants carry data: which one remains in the reading text."""
import json
import random
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from pydantic import BaseModel

from mnemosyne.literature import DRAFTING, Writer, prose_fields, settle
from mnemosyne.weave import DecodeError, fountain, payload, variants

WORDS = ['море', 'ветер', 'дом', 'окно', 'сад', 'мост', 'снег', 'свет', 'река', 'камень', 'лес', 'берег']


def draft(places, seed=1):
    rng = random.Random(seed)
    parts = []
    for i in range(places):
        options = rng.sample(WORDS, rng.randint(2, 4))
        parts.append(f'Фраза {i}: {{{"|".join(options)}}} у дороги.')
    return ' '.join(parts)


class CodecTests(unittest.TestCase):
    def test_places_follow_the_rules_and_plain_reads_the_first_variant(self):
        pieces, tail = variants.places('Был {холодный|серый} день, {а|аа} и {один} {x|x}.')
        self.assertEqual([o for _, o in pieces], [['холодный', 'серый']])
        self.assertEqual(variants.plain('Был {холодный|серый} день.'), 'Был холодный день.')

    def test_reading_text_recovers_every_choice(self):
        entries = [{'id': '/a', 'markup': draft(30)}, {'id': '/b', 'markup': draft(20, 2)}]
        digits = [random.Random(3).randrange(r) for r in variants.radices(entries)]
        self.assertEqual([d for e in variants.realize(entries, digits) for d in variants.read(e)], digits)

    def test_frames_survive_in_the_variants_and_tampering_is_rejected(self):
        key = X25519PrivateKey.generate()
        entries = [{'id': '/night', 'markup': draft(2000)}]
        envelope = payload.seal(b'cluster', key.public_key(), context=fountain.DOMAIN)
        encoder = fountain.Encoder(envelope, 128, key)
        frames = [encoder.frame(i) for i in range(2)]
        volume = variants.encode_many(entries, frames, key)
        self.assertEqual(variants.decode_many(json.loads(json.dumps(volume)), key), frames)
        self.assertNotIn('{', volume['entries'][0]['text'])
        edited = json.loads(json.dumps(volume))
        edited['entries'][0]['markup'] = edited['entries'][0]['markup'].replace('у дороги', 'у порога', 1)
        with self.assertRaises(DecodeError):
            variants.decode_many(edited, key)

    def test_collect_finds_prose_with_variants_by_path(self):
        record = {'entries': [{'result': {'diary': 'Я {шёл|брёл} домой.', 'plan_json': '{}'}}], 'status': 'x'}
        self.assertEqual(variants.collect(record), [{'id': '/entries/0/result/diary', 'markup': 'Я {шёл|брёл} домой.'}])


class Draft(BaseModel):
    diary: str
    plan_json: str
    verdict: str


class WriterTests(unittest.TestCase):
    def test_only_prose_keeps_variants(self):
        self.assertEqual(prose_fields(Draft), ['diary'])
        result = settle(Draft(diary='Я {шёл|брёл}.', plan_json='{"a": "{x|y}"}', verdict='{accept|rewrite}'), ['diary'])
        self.assertEqual((result.diary, result.plan_json, result.verdict), ('Я {шёл|брёл}.', '{"a": "x"}', 'accept'))

    def test_drafting_instruction_only_while_a_night_drafts(self):
        seen = []
        w = Writer([], backend='none', data_class='art')
        w._ask = lambda system, *a, **k: seen.append(system) or Draft(diary='d', plan_json='{}', verdict='accept')
        w.ask('s', 'p', Draft, 'diary')
        token = DRAFTING.set(True)
        try:
            w.ask('s', 'p', Draft, 'diary')
        finally:
            DRAFTING.reset(token)
        self.assertEqual(seen[0], 's')
        self.assertIn('{вариант|вариант|вариант}', seen[1])
        self.assertIn('diary', seen[1])


class NightTests(unittest.TestCase):
    def test_notebook_variants_carry_frames_alongside_scores(self):
        from tests.test_composer_transport import cluster, night
        from mnemosyne.restore import recover_works
        from mnemosyne.state import ledger
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = X25519PrivateKey.generate()
            n = night(tmp/'n', cluster(), tmp/'ledger', '2025-07-01T00:00:00', works=2)
            n.work_id = 'leonia-0001-w00001'
            n.artist = type('A', (), {'id': 'a'})()
            n.life.biographies = {'a': type('B', (), {'chapters': [{'text': 'old'}]})()}
            n.record['entries'] = [{'step': 'diary', 'result': {'diary': draft(2600)}}]
            n.record['chapter'] = 'Глава: он {вернулся|пришёл} к {морю|реке}.'
            n.backup(key)
            report = n.record['backup']
            self.assertIn('leonia-0001-w00001-notebook', report['carriers'])
            self.assertNotIn('{', n.record['entries'][0]['result']['diary'])
            self.assertEqual(n.record['apparatus']['/chapter'], 'Глава: он {вернулся|пришёл} к {морю|реке}.')
            self.assertEqual(n.life.biographies['a'].chapters[-1]['text'], n.record['chapter'])
            _, objects, rep = recover_works(tmp/'n/woven', key)
            self.assertEqual({o['kind'] for o in objects}, {'Namespace', 'ConfigMap', 'Deployment'})


if __name__ == '__main__':
    unittest.main()
