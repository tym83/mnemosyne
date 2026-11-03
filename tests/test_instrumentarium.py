"""Instrument contracts, sounding/written pitch, scheduling and replay."""
import copy
import json
from pathlib import Path
import random
import tempfile
import unittest
from music21 import converter, note, stream, midi
from scheherazade.music.instrumentarium import (REGISTRY, ENSEMBLES, ensemble,
    notation_instrument, notation_clef, validate_registry, sample_patch, velocity_limits)
from scheherazade.music.orchestration import Event,Line,orchestrate
from scheherazade.music.native_bank import regions,check_coverage,playback_patch
from scheherazade.music.schools.performance import write_midi
from scheherazade.music.distinctness import features,compare


class InstrumentariumTests(unittest.TestCase):
    def plan(self,ens='string_quartet'):
        return {'ensemble':ens,'duration':40,'tempo':60,'title':'Test'}

    def line(self,pitches=(64,),instrument=None,role='melody',technique=None,duration=4):
        return Line('line',role,(Event(0,duration,pitches,64,technique),),(min(pitches),max(pitches)),.5,'dark',instrument)

    def test_registry_and_symphony(self):
        validate_registry()
        players=ensemble('symphony_orchestra')
        self.assertEqual(sum(p.instrument=='horn' for p in players),4)
        self.assertEqual(sum(p.instrument=='trumpet' for p in players),3)
        self.assertEqual(sum('trombone' in p.instrument for p in players),3)
        self.assertEqual(sum(p.spec['section'] for p in players),5)
        self.assertTrue(all(p.divisi>1 for p in players if p.spec['section']))
        self.assertEqual(sum(p.instrument=='flute' for p in players),3)

    def test_solo_is_never_section(self):
        for p in ensemble('string_quartet'):
            self.assertFalse(p.spec['section'])
            self.assertIn('Solo',sample_patch(p.instrument,'arco')[1])
        with self.assertRaisesRegex(ValueError,'no licensed sample'):
            sample_patch('soprano','sustain')
        with self.assertRaises(ValueError):sample_patch('violin','sul_ponticello')

    def test_custom_and_invalid_ensembles(self):
        self.assertEqual(len(ensemble([{'instrument':'horn','count':4}])),4)
        for spec in ([],[{'instrument':'kazoo'}],[{'instrument':'flute','divisi':2,'players':2}],
                     [{'instrument':'viola_section','players':2,'divisi':3}], [{'instrument':'horn','pan':float('nan')}]):
            with self.assertRaises(ValueError):ensemble(spec)

    def test_transposition_roundtrip_every_pitched_instrument(self):
        with tempfile.TemporaryDirectory() as folder:
            for name,spec in REGISTRY.items():
                if spec.get('unpitched'):continue
                with self.subTest(name=name):
                    s=stream.Score();s.atSoundingPitch=True;p=stream.Part()
                    p.insert(0,notation_instrument(name));p.insert(0,notation_clef(name));p.append(note.Note(spec['comfortable'][0]));s.insert(0,p)
                    written=s.toWrittenPitch()
                    self.assertEqual(written.parts[0].recurse().notes.first().pitch.midi,
                                     spec['comfortable'][0]-spec['sounding_minus_written'])
                    path=Path(folder)/'test.musicxml';s.write('musicxml',fp=path)
                    recovered=converter.parse(path).toSoundingPitch()
                    self.assertEqual(recovered.parts[0].recurse().notes.first().pitch.midi,spec['comfortable'][0])

    def test_determinism_no_mutation(self):
        lines=[self.line()];plan=self.plan();original=copy.deepcopy(plan);state=random.getstate()
        _,a=orchestrate(lines,plan);_,b=orchestrate(lines,plan)
        self.assertEqual(a,b);self.assertEqual(plan,original);self.assertEqual(state,random.getstate())

    def test_range_and_technique_rejection(self):
        for line in (self.line((20,),instrument='violin'),self.line((90,),instrument='cello'),
                     self.line((64,),instrument='violin',technique='sul_ponticello')):
            with self.assertRaises(ValueError):orchestrate([line],self.plan())
        with self.assertRaises(ValueError):velocity_limits('timpani',60.5)
        self.assertEqual(velocity_limits('timpani',55.5),(20,120))

    def test_required_techniques_cannot_be_ignored_by_shared_api(self):
        plan=self.plan();plan['required_techniques']=['sul_ponticello']
        with self.assertRaisesRegex(ValueError,'Required techniques'):
            orchestrate([self.line()],plan)

    def test_breaths_and_divisi(self):
        _,a=orchestrate([self.line(instrument='flute',duration=20)],self.plan('wind_quintet'))
        events=[e for p in a['players'] for e in p['events']]
        self.assertGreater(len(events),1)
        self.assertTrue(all(e['duration']<8 for e in events))
        _,a=orchestrate([self.line((60,64,67))],self.plan([{'instrument':'violin_1_section','players':6,'divisi':3}]))
        self.assertEqual(sum(bool(p['events']) for p in a['players']),3)
        self.assertEqual(sorted(p['events'][0]['pitches'][0] for p in a['players']),[60,64,67])
        with self.assertRaises(ValueError):orchestrate([self.line((60,64,67,71))],self.plan([{'instrument':'violin_1_section','players':6,'divisi':3}]))

    def test_midi_multiport(self):
        score=stream.Score()
        for i in range(32):
            part=stream.Part();part.insert(0,notation_instrument('flute'));part.append(note.Note(60));score.insert(0,part)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'score.mid';write_midi(score,path,60)
            data=path.read_bytes();self.assertIn(b'\xff\x21\x01\x02',data)
            f=midi.MidiFile();f.open(path);f.read();f.close();self.assertEqual(len(f.tracks),32)

    def test_native_regions_inheritance_velocity_and_rr(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sample.wav').write_bytes(b'sample')
            (root/'inc.sfz').write_text('<region> sample=sample.wav seq_position=1\n<region> sample=sample.wav seq_position=2')
            path=root/'main.sfz';path.write_text('<global> lokey=60 hikey=72\n<group> lovel=40 hivel=80 seq_length=2\n#include "inc.sfz"')
            zones=regions(path);self.assertEqual([z['seq_position'] for z in zones],[1,2]);self.assertEqual(zones[0]['low'],60)
            patch={'instrument':'test','technique':'sustain','regions':zones}
            check_coverage(patch,64,60)
            for pitch,vel in [(59,60),(64,81)]:
                with self.assertRaises(ValueError):check_coverage(patch,pitch,vel)

    def test_unpitched_midi_and_exact_divisi_player_count(self):
        from scheherazade.music.ensemble_demos import demo
        p,lines=demo('percussion_ensemble');score,assignment=orchestrate(lines,p)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'percussion.mid';write_midi(score,path,60)
            self.assertIn(bytes([0x99,35]),path.read_bytes())
        _,assignment=orchestrate([self.line()],self.plan([{'instrument':'violin_1_section','players':14,'divisi':4}]))
        self.assertEqual(sum(p['players'] for p in assignment['players']),14)

    def test_existing_symphony_adapter_preserves_source_and_rejects_tempo_loss(self):
        from music21 import tempo
        from scheherazade.music.orchestration import orchestrate_existing
        score=stream.Score();part=stream.Part();part.insert(0,notation_instrument('flute'))
        part.insert(0,tempo.MetronomeMark(number=60));part.append(note.Note(64,quarterLength=4));score.insert(0,part)
        arranged,plan,assignment=orchestrate_existing(score,{'ensemble':'wind_quintet'})
        self.assertEqual(plan['duration'],4);self.assertIn('score-partwise',plan['source_musicxml'])
        self.assertEqual(len(arranged.parts),5)
        part.insert(2,tempo.MetronomeMark(number=120))
        with self.assertRaisesRegex(ValueError,'one tempo'):orchestrate_existing(score)

    def test_distinctness_includes_each_feature_family(self):
        s,_=orchestrate([self.line()],self.plan())
        f=features(s,60);self.assertEqual(set(f),{'register','density','interval_classes','durations','dynamics','timbres','seconds'})
        report=compare({'a':f,'b':copy.deepcopy(f)})
        self.assertEqual(len(report['identical_pairs']),1)
        g=copy.deepcopy(f);g['timbres']={'tuba':1}
        self.assertGreater(compare({'a':f,'b':g})['closest_pairs'][0]['distance'],0)


if __name__=='__main__':unittest.main()
