"""Small contract tests; the population test also runs in the workshop pod."""
import json
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from mnemosyne.atelier import Atelier, KINDS
from mnemosyne.lineage import Lineage, Parameters, LifeWords

BORN = datetime(2025, 1, 1, tzinfo=timezone.utc)
HEAVY = dict(strain=.8, scars=.8, loss=.8, turbulence=.8)


class LineageTests(unittest.TestCase):
    def test_illumination_seeds_existing_idea_stage_without_bypassing_critic(self):
        from mnemosyne.artist import SelfPortrait, statement
        calls = []
        def ask(writer, system, prompt, schema, step, **kwargs):
            calls.append((step, prompt))
            values = {k: {} if f.annotation is dict else [] if getattr(f.annotation, '__origin__', None) is list else 'text'
                      for k, f in schema.model_fields.items()}
            if 'verdict' in values:
                values['verdict'] = 'accept'
            return schema(**values)
        portrait = SelfPortrait(name='test', portrait='test', wounds=[], loves=[], fears=[],
                                what_i_am_as_artist='test')
        with patch('mnemosyne.artist.Writer.ask', ask), patch('mnemosyne.artist.theory', return_value=''):
            _, history = statement(portrait, 'literature', [], [],
                                   illumination={'idea': 'a supplied insight', 'problem': 'an earlier problem'})
        self.assertIn('a supplied insight', calls[0][1])
        self.assertIn('an earlier problem', calls[0][1])
        self.assertEqual([c[0] for c in calls], ['statement:0', 'interrogation:0'])
        self.assertEqual(history[0]['interrogation']['verdict'], 'accept')

    def test_real_verdict_and_insight_still_face_verification(self):
        life = Lineage('test', BORN)
        a = life.artists[0]
        a.pending_idea = {'idea': 'supplied idea', 'strength': .95}
        w = life._work(a, observation={'feature': [0, 0, 0, 0], 'novelty': .1,
                                      'quality': .9, 'verdict': 'repetition',
                                      'process': {'draft': 'external-ref'}})
        self.assertFalse(w['synthetic'])
        self.assertEqual(w['verdict'], 'repetition')
        self.assertEqual(a.repetition_run, 1)
        self.assertIsNone(a.pending_idea)
        self.assertEqual(life.events[-1]['kind'], 'verification')

    def test_determinism_resume_and_births(self):
        a, b = Lineage('test', BORN, 18), Lineage('test', BORN, 18)
        for _ in range(250):
            a.step(HEAVY)
            b.step(HEAVY)
        b = Lineage.restore(json.loads(json.dumps(b.state())))
        for _ in range(250):
            a.step(HEAVY)
            b.step(HEAVY)
            self.assertLessEqual(len(a.working()), 3)
        self.assertEqual(a.state(), b.state())
        self.assertEqual(a.artists[0].birth, BORN.isoformat())
        for artist in a.artists:
            self.assertTrue(artist.birth)
            self.assertEqual(sum(e['kind'] == 'birth' and e['artist'] == artist.id for e in a.events), 1)

    def test_silent_alive_replaced_and_dead_cannot_work(self):
        life = Lineage('test', BORN)
        a = life.artists[0]
        life._silence(a, 'test')
        life.step({})
        self.assertEqual(a.status, 'silent')
        self.assertEqual(len(life.artists), 2)
        life._die(a, 'test')
        size = len(a.catalogue)
        self.assertEqual(a.catalogue[-1]['kind'], 'last_piece')
        with self.assertRaises(ValueError):
            life._work(a)
        for _ in range(30):
            life.step({})
        self.assertEqual(len(a.catalogue), size)
        self.assertTrue(all(w['night'] <= a.death_night for w in a.catalogue))
        kinds = [e['kind'] for e in life.events if e['artist'] == a.id]
        self.assertLess(kinds.index('secret_miracle'), kinds.index('last_work'))
        self.assertLess(kinds.index('last_work'), kinds.index('death'))

    def test_illness_needs_inner_crisis_and_has_course(self):
        p = replace(Parameters(), illness_rate=1, illness_death=0,
                    onset_nights=2, crisis_nights=2, recovery_nights=2)
        life = Lineage('test', BORN, parameters=p)
        a = life.artists[0]
        a.heavy = 100
        life._illness(a)
        self.assertFalse(a.illness)
        a.vitality, a.rejections = .2, 10
        life._illness(a)
        self.assertEqual(a.illness, 'onset')
        for expected in ('crisis', 'recovery', ''):
            life.night += 2
            life._illness(a)
            self.assertEqual(a.illness, expected)
        self.assertTrue(any(e['kind'] == 'period' for e in life.events))

    def test_solitude_prevents_incoming_and_outgoing_relationships(self):
        life = Lineage('test', BORN)
        a = life.artists[0]
        a.solitude = 1
        b = life._birth(a)
        self.assertFalse(b.teachers)
        for source, target in ((a, b), (b, a)):
            for relation in ('friendship', 'rediscovery'):
                self.assertFalse(life.influence(source, target, relation, .6))
        self.assertFalse(life.influences)
        a.solitude = b.solitude = 0
        self.assertTrue(life.influence(a, b, 'friendship', .6))
        self.assertEqual(len(life.influences), 1)

    def test_prolonged_illness_resumes_into_working_changed_voice(self):
        p = replace(Parameters(), illness_death=0, prolonged_rate=1)
        life = Lineage('test', BORN, parameters=p)
        a = life.artists[0]
        a.status, a.illness, a.resilience = 'ill', 'crisis', 0
        life.night = p.crisis_nights
        life._illness(a)
        self.assertEqual(a.illness, 'prolonged')
        life.night += p.prolonged_nights - 1
        life._illness(a)
        self.assertFalse(a.altered_voice)
        restored = Lineage.restore(json.loads(json.dumps(life.state())))
        for branch in (life, restored):
            artist = branch.artists[0]
            branch.night += 1
            branch._illness(artist)
            self.assertEqual(artist.illness, 'changed')
            self.assertEqual(artist.status, 'ill')
            self.assertTrue(artist.altered_voice)
            change_night = branch.night
            for _ in range(20):
                branch.night += 1
                branch._illness(artist)
                branch.record_work(artist.id, dict(feature=[0, 0, 0, 0],
                                   novelty=.8, quality=.8, verdict='accept'))
            self.assertEqual(sum(w['night'] > change_night for w in artist.catalogue), 20)
            self.assertFalse(any(e['kind'] == 'recovered' for e in branch.events))
            self.assertEqual(artist.health, .6)
        self.assertEqual(life.state(), restored.state())

    def test_changed_voice_waits_for_vacancy_without_reviving_renunciation(self):
        p = replace(Parameters(), spaces=1, work_rate=0, accident=0, age_hazard=0)
        for renounced in (False, True):
            life = Lineage('test', BORN, parameters=p)
            a = life.artists[0]
            life._silence(a, 'exhaustion')
            a.renounced = renounced
            occupant = life._birth()
            a.illness = 'prolonged'
            life.night = p.prolonged_nights - 1
            life.step({})
            self.assertTrue(a.altered_voice)
            self.assertEqual(a.status, 'silent')
            self.assertEqual(a.return_ready, not renounced)
            self.assertEqual(life.working(), [occupant])
            life._silence(occupant, 'test')
            life.step({})
            self.assertEqual(a.status, 'silent' if renounced else 'ill')
            self.assertEqual(len(life.working()), 1)

    def test_master_and_repetition_silence(self):
        p = replace(Parameters(), mastery_nights=3, work_rate=0)
        life = Lineage('test', BORN, parameters=p)
        a = life.artists[0]
        life._work(a)['verdict'] = 'accept'
        for _ in range(3):
            life.step({})
        a = life.artists[0]
        self.assertTrue(a.master)
        a.repetition_run = p.repetition_limit
        life.step({})
        self.assertEqual(a.status, 'silent')
        self.assertFalse(any(e['kind'] == 'death' for e in life.events))

    def test_no_cluster_incident_literalism(self):
        a, b = Lineage('test', BORN), Lineage('test', BORN)
        for _ in range(30):
            a.step({'qualities': HEAVY, 'pod_crash': True})
            b.step({'qualities': HEAVY, 'pod_crash': False})
        self.assertEqual(a.state(), b.state())

    def test_words_cannot_change_fate_and_resume(self):
        class FakeWriter:
            def __init__(self, notebook):
                self.notebook = notebook
            def ask(self, system, prompt, schema, step):
                self.notebook.append({'step': step})
                return LifeWords(chapter='A life.', diary='A page.', letter='', last_idea='',
                                 portrait='A portrait.', name='Someone', image='')
        life = Lineage('test', BORN)
        for _ in range(5):
            life.step({})
        state = json.loads(json.dumps(life.state()))
        life.write_words(FakeWriter)
        self.assertEqual(state['events'], life.events)
        self.assertEqual(state['rng'], json.loads(json.dumps(life.rng.getstate())))
        self.assertTrue(all(c['text'] for b in life.biographies.values() for c in b.chapters))
        size = sum(len(a.notebook) for a in life.artists)
        life.write_words(FakeWriter)
        self.assertEqual(size, sum(len(a.notebook) for a in life.artists))

    def test_persisted_objects_and_references(self):
        life = Lineage('test', BORN)
        life._work(life.artists[0])
        with tempfile.TemporaryDirectory() as tmp:
            atelier = Atelier('test', Path(tmp))
            atelier.lineage(life)
            counts = atelier.write()
            self.assertEqual(counts['Artist'], 1)
            self.assertEqual(counts['Biography'], 1)
            names = {o['metadata']['name'] for o in atelier.objects}
            for biography in life.biographies.values():
                for c in biography.chapters:
                    self.assertTrue(set(c['works'] + c['drafts']) <= names)
            self.assertIn('Artist', KINDS)
            self.assertTrue((Path(tmp) / 'test/lives.md').exists())
            restored = Lineage.from_objects(atelier.objects, 'test')
            for _ in range(20):
                life.step(HEAVY)
                restored.step(HEAVY)
            self.assertEqual(life.state(), restored.state())


class BiographyCarrierTests(unittest.TestCase):
    def test_shared_frames_roundtrip_and_capacity(self):
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from mnemosyne.weave import frames, payload
        from mnemosyne.weave.biography import capacity, frame_payload
        key = X25519PrivateKey.generate()
        data = b'lives and notebook' * 100
        # One large passage: verify framing, not an invented prose codec.
        contexts = [b'canonical biography text']
        blocks = frame_payload(data, key, contexts, 1024)
        self.assertEqual(frames.assemble([frames.unpack(blocks[0], key, contexts[0])], key), data)
        self.assertEqual(capacity()['payload_bytes_per_frame'], 0)
        self.assertEqual(capacity(800)['payload_bytes_per_frame'], 80)
        with self.assertRaises(ValueError):
            frame_payload(data, key, contexts, 0)
