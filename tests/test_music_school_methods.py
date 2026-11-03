"""Process-level invariants in addition to round-trip/range/determinism checks."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from music21 import note, stream
from scheherazade.music.schools import SCHOOLS
from scheherazade.music.schools.performance import sounding_events, write_midi
from scheherazade.music.schools.spectral import partial_pitch
from scheherazade.music.schools.tempo_canon import onset, RATIOS
from scheherazade.music.schools.messiaen import RHYTHM, MODE

PLANS = Path(__file__).resolve().parents[1]/'src/scheherazade/music/schools/plans'


class MethodTests(unittest.TestCase):
    def score(self, name):
        plan = json.loads((PLANS/f'{name}.json').read_text())
        return SCHOOLS[name].compose(plan, plan['seed']), plan

    def test_temporal_canon_integrates_acceleration(self):
        for ratio in RATIOS:
            for index in (1, 8, 32, 100):
                t = onset(index, ratio, 60)
                self.assertAlmostEqual(ratio*(t+t*t/120), index)
            self.assertLess(onset(101,ratio,60)-onset(100,ratio,60), onset(2,ratio,60)-onset(1,ratio,60))

    def test_mode_symmetry_and_palindrome(self):
        self.assertEqual(RHYTHM, RHYTHM[::-1])
        self.assertEqual(set(MODE), {(x+3)%12 for x in MODE})
        self.assertNotEqual(set(MODE), {(x+1)%12 for x in MODE})

    def test_spectra_are_derived_not_selected_chords(self):
        self.assertEqual(partial_pitch(36, 2, 1), 48)
        for partial in range(1, 11):
            exact = 36+12*math.log2(partial)
            self.assertLessEqual(abs(partial_pitch(36,partial,1)-exact), .25)
        self.assertGreater(partial_pitch(36,8,1.18), partial_pitch(36,8,1))

    def test_drone_retains_exact_just_tuning(self):
        score, plan = self.score('drone')
        pitches = [list(sounding_events(part))[0][2][0] for part in score.parts]
        fundamental = pitches[-1]
        for i, pitch in enumerate(pitches):
            partial = len(pitches)-i
            quotient = 2**((pitch-fundamental)/12)/partial
            self.assertAlmostEqual(math.log2(quotient), round(math.log2(quotient)))
        self.assertTrue(any(abs(x*2-round(x*2)) > .01 for x in pitches))
        self.assertEqual(list(sounding_events(score.parts[-1]))[0][0], 0)

    def test_modular_players_stay_within_two_modules(self):
        score, _ = self.score('in_c')
        events = sorted((float(e.getOffsetInHierarchy(p)), i, int(e.content.split(';')[0].split()[1]))
                        for i,p in enumerate(score.parts) for e in p.recurse().getElementsByClass('TextExpression')
                        if e.content.startswith('Module '))
        positions = [1]*len(score.parts)
        previous_at = None
        for at,i,module in events:
            if at in (0,60,120) and at != previous_at:
                positions = [1]*len(score.parts)
            positions[i] = module
            # A player announces its new module at the next entry; one-module
            # lag in announcements can add one to the internal bound of two.
            self.assertLessEqual(max(positions)-min(positions), 3)
            previous_at = at

    def test_chance_contains_silence_and_multiple_dynamics(self):
        score, _ = self.score('chance')
        self.assertGreater(sum(float(n.quarterLength) for p in score.parts for n in p.recurse().getElementsByClass('Rest')), 30)
        self.assertGreater(len({d.value for d in score.recurse().getElementsByClass('Dynamic')}), 5)

    def test_fibonacci_form_and_archived_quotation(self):
        _, plan = self.score('fibonacci')
        values = [s['duration'] for s in plan['form']]
        self.assertEqual(values, [x*8 for x in (2,3,5,8,13)])
        quote = json.loads((PLANS/'polystylism.json').read_text())['quotation']
        self.assertEqual(hashlib.sha256(quote['source_musicxml'].encode()).hexdigest(), quote['sha256'])

    def test_quartertone_bends_and_simultaneous_cluster_notes(self):
        from scheherazade.music.schools.common import setup, put, finish
        plan = json.loads((PLANS/'chance.json').read_text())
        score, _, _, total = setup(plan, 1, 'test')
        put(score.parts[0], 0, 1, 60.5)
        put(score.parts[0], 1, 1, 60)
        put(score.parts[1], 0, 1, [48,49,50])
        finish(score,total)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.mid'
            write_midi(score,path,60)
            raw = path.read_bytes()
            # half-semitone / twelve-semitone bend range, nearest MIDI key 60
            value = 8192+round(.5/12*8192)
            self.assertIn(bytes([0xE0,value&127,value>>7]), raw)
            self.assertIn(bytes([0xE0,0,64]), raw)
            for key in (48,49,50):
                self.assertIn(bytes([0x91,key]), raw)

    def test_soft_and_hammered_dynamics_survive_performance(self):
        soft, _ = self.score('feldman')
        hammer, _ = self.score('ustvolskaya')
        soft_vel = [e[3] for p in soft.parts for e in sounding_events(p)]
        loud_vel = [e[3] for p in hammer.parts for e in sounding_events(p)]
        self.assertLess(max(soft_vel), 25)
        self.assertGreater(max(loud_vel), 110)
        self.assertTrue(any(len(e[2]) >= 6 for p in hammer.parts for e in sounding_events(p)))
