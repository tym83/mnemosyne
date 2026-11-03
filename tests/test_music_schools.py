"""Musical invariants; no renderer or sample downloads required."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from music21 import converter, midi
from scheherazade.music.schools import SCHOOLS
from scheherazade.music.schools.common import ENSEMBLES, analyze
from scheherazade.music.schools.serial import row_forms
from scheherazade.music.schools.performance import write_midi
from scheherazade.music.render import note_events

PLANS = Path(__file__).resolve().parents[1]/'src/scheherazade/music/schools/plans'


def fingerprint(score):
    # Object IDs and serialization dates are not musical content.
    return [[(type(e).__name__,float(e.getOffsetInHierarchy(p)),
              float(e.quarterLength),str(getattr(e,'value','')),
              tuple(x.ps for x in getattr(e,'pitches',())),
              tuple(type(a).__name__ for a in getattr(e,'articulations',())),
              str(getattr(e,'tie','')),str(getattr(e,'content','')))
             for e in p.recurse() if not e.isStream] for p in score.parts]


class SchoolTests(unittest.TestCase):
    def plan(self,name):
        return json.loads((PLANS/f'{name}.json').read_text())

    def test_determinism_and_no_plan_or_global_rng_mutation(self):
        for name,school in SCHOOLS.items():
            with self.subTest(school=name):
                plan=self.plan(name)
                original=copy.deepcopy(plan)
                state=random.getstate()
                a=school.compose(plan,123)
                b=school.compose(plan,123)
                self.assertEqual(fingerprint(a),fingerprint(b))
                self.assertEqual(random.getstate(),state)
                self.assertEqual(plan,original)
                self.assertNotEqual(note_events(a),note_events(school.compose(plan,124)))

    def test_ranges_duration_and_nonempty_for_every_ensemble(self):
        for name,school in SCHOOLS.items():
            for ensemble in ENSEMBLES:
                for seed in (0,23):
                    with self.subTest(school=name,ensemble=ensemble,seed=seed):
                        plan=self.plan(name)
                        plan['ensemble']=ensemble
                        info=analyze(school.compose(plan,seed),plan)
                        self.assertEqual(info['score_seconds'],plan['duration'])
                        self.assertEqual(info['empty_parts'],0)

    def test_xml_roundtrip_and_midi(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name,school in SCHOOLS.items():
                with self.subTest(school=name):
                    plan=self.plan(name)
                    score=school.compose(plan,plan['seed'])
                    path=Path(tmp)/'score.musicxml'
                    score.write('musicxml',fp=path)
                    recovered=converter.parse(path).toSoundingPitch()
                    self.assertEqual(note_events(score.stripTies()),note_events(recovered.stripTies()))
                    path=Path(tmp)/'score.mid'
                    write_midi(score,path,plan['tempo'])
                    mf=midi.MidiFile()
                    mf.open(path); mf.read(); mf.close()
                    self.assertEqual(len(mf.tracks),len(score.parts))
                    self.assertTrue(all(any(e.type==midi.ChannelVoiceMessages.NOTE_ON for e in t.events) for t in mf.tracks))

    def test_invalid_plans(self):
        for patch in ({'duration':float('nan')},{'tempo':0},{'ensemble':'kazoo'},{'form':[]}):
            plan=self.plan('serial'); plan.update(patch)
            with self.assertRaises(ValueError):
                SCHOOLS['serial'].compose(plan,0)

    def test_row_forms_and_complete_aggregates(self):
        row=[0,1,4,2,7,5,8,6,11,9,3,10]
        p,i,r,ri=row_forms(row)
        self.assertEqual(p,list(reversed(r)))
        self.assertEqual(i,list(reversed(ri)))
        self.assertTrue(all(sorted(x)==list(range(12)) for x in (p,i,r,ri)))
        plan=self.plan('serial')
        score=SCHOOLS['serial'].compose(plan,1)
        events=sorted((float(n.getOffsetInHierarchy(p)),n.pitch.pitchClass) for p in score.parts for n in p.recurse().notes)
        for start in range(0,len(events),12):
            self.assertEqual(sorted(pc for _,pc in events[start:start+12]),list(range(12)))

    def test_t_voice_on_triad(self):
        score=SCHOOLS['tintinnabuli'].compose(self.plan('tintinnabuli'),11)
        self.assertTrue(all(n.pitch.pitchClass in (0,3,7) for n in score.parts[1].recurse().notes))


if __name__=='__main__':
    unittest.main()
