"""Pedal notation/MIDI agreement, data-driven release and safe legato."""
import json
from pathlib import Path
import tempfile
import unittest
from music21 import converter, instrument, midi, note, spanner, stream
from mnemosyne.music.resonance import apply, annotate_xml, read_pedals
from mnemosyne.music.schools import SCHOOLS
from mnemosyne.music.schools.performance import sounding_events, write_midi
from mnemosyne.music.instrumentarium import ROOT, REGISTRY, release_profile
from mnemosyne.music.native_bank import playback_patch, regions
from unittest.mock import patch
import wave


class ResonanceTests(unittest.TestCase):
    def test_pedal_xml_and_midi_same_timeline(self):
        plan = json.loads((ROOT/'schools/plans/tintinnabuli.json').read_text())
        score = apply(SCHOOLS['tintinnabuli'].compose(plan,plan['seed']),plan)
        with tempfile.TemporaryDirectory() as d:
            xml = Path(d)/'score.musicxml'; mid = Path(d)/'score.mid'
            score.write('musicxml',fp=xml); annotate_xml(xml,score)
            recovered = read_pedals(xml,converter.parse(xml))
            self.assertEqual(recovered.parts[0].editorial.sustain_pedal, [(0,127),(48,0)])
            write_midi(recovered,mid,plan['tempo'])
            mf=midi.MidiFile(); mf.open(mid); mf.read(); mf.close()
            for track in mf.tracks:
                at=0; pedals=[]
                for event in track.events:
                    if isinstance(event,midi.DeltaTime):at+=event.time
                    elif event.type==midi.ChannelVoiceMessages.CONTROLLER_CHANGE and event.parameter1==64:
                        pedals.append((at,event.parameter2))
                self.assertEqual(pedals,[(0,127),(48*960,0)])

    def test_serial_no_pedal_and_harp_no_damper_pedal(self):
        for school in ('serial','tintinnabuli'):
            s=stream.Score();p=stream.Part();p.insert(0,instrument.Harp());p.append(note.Note());s.append(p)
            apply(s,{'school':school,'duration':1,'tempo':60})
            self.assertEqual(p.editorial.sustain_pedal,[])

    def test_legato_overlap_and_rest_and_repeated_key(self):
        for gap,pitch,overlap in ((0,'D4',True),(.25,'D4',False),(0,'C4',False)):
            p=stream.Part();a=note.Note('C4');b=note.Note(pitch)
            p.insert(0,a);p.insert(1+gap,b);p.insert(0,spanner.Slur(a,b))
            events=list(sounding_events(p,60))
            self.assertAlmostEqual(events[0][1],1.03 if overlap else 1.)

    def test_release_registry_and_sfz(self):
        for name in REGISTRY:self.assertGreater(release_profile(name)['release_seconds'],0)
        self.assertGreater(release_profile('harp')['release_seconds'],release_profile('piano')['release_seconds'])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'fixture').mkdir();wav=root/'fixture/sample.wav'
            with wave.open(str(wav),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*8000)
            (root/'fixture/patch.sfz').write_text('<global> ampeg_release=0.01\n<region> sample=sample.wav key=60 loop_mode=no_loop')
            with patch('mnemosyne.music.native_bank.sample_patch',return_value=('fixture','patch.sfz')), patch('mnemosyne.music.sample_sustain.audio_info',return_value={'seconds':1,'rate':8000,'channels':1}):
                playback_patch(root,'harp','sustain',root/'playback.sfz')
            z=regions(root/'playback.sfz')[0]
            self.assertEqual(float(z['opcodes']['ampeg_release']),release_profile('harp')['release_seconds'])
            self.assertEqual(z['opcodes']['loop_mode'],'no_loop')

if __name__=='__main__': unittest.main()

class SustainTests(unittest.TestCase):
    def test_crossfade_continuity_keeps_attack_and_source_tail(self):
        import numpy as np
        from mnemosyne.music.sample_sustain import crossfade_loop
        rate=8000
        source=np.sin(np.arange(rate*2)*.117)
        actual,start,end=crossfade_loop(source,rate)
        self.assertTrue(np.array_equal(source[:start],actual[:start]))
        self.assertTrue(np.array_equal(source[end+1:],actual[end+1:]))
        self.assertAlmostEqual(actual[end],source[start-1])
        self.assertLess(abs(actual[end]-actual[start]),.12)

    def test_library_loop_is_preserved_and_release_sample_is_not_looped(self):
        from mnemosyne.music.sample_sustain import prepare_region
        profile={'release_seconds':.18,'sustained':True}
        zone={'sample':'fixture.wav','opcodes':{'loop_mode':'loop_continuous','loop_start':'100','loop_end':'7999'}}
        with patch('mnemosyne.music.sample_sustain.audio_info',return_value={'rate':8000,'seconds':2,'channels':1}):
            overrides,report=prepare_region(zone,profile,Path('/unused/patch.sfz'))
            self.assertEqual(overrides['loop_start'],100)
            self.assertEqual(overrides['loop_end'],7999)
            self.assertEqual(report['sustain'],'library-loop')
            zone['trigger']='release'
            self.assertNotIn('loop_mode',prepare_region(zone,profile,Path('/unused/patch.sfz'))[0])

    def test_measure_detects_an_abrupt_cut(self):
        import numpy as np
        from mnemosyne.music.resonance_measure import measure
        rate=8000
        data=np.ones(rate*2)*.1;data[rate:]=0
        report=measure(data,[1.],1,1,rate)
        self.assertEqual(report['drops_over_20db'],1)
        self.assertAlmostEqual(report['boundaries'][0]['rms_before_50ms_dbfs'],-20)
        self.assertLess(report['boundaries'][0]['rms_after_150ms_dbfs'],-100)

class MidiLegatoTests(unittest.TestCase):
    def test_actual_midi_overlaps_slurred_notes(self):
        p=stream.Part();p.insert(0,instrument.Flute())
        a=note.Note('C4');b=note.Note('D4');p.insert(0,a);p.insert(1,b);p.insert(0,spanner.Slur(a,b))
        score=stream.Score();score.append(p)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'legato.mid';write_midi(score,path,60)
            mf=midi.MidiFile();mf.open(path);mf.read();mf.close()
            at=0;off=None;on=None
            for e in mf.tracks[0].events:
                if isinstance(e,midi.DeltaTime):at+=e.time
                elif e.type==midi.ChannelVoiceMessages.NOTE_OFF and e.pitch==60:off=at
                elif e.type==midi.ChannelVoiceMessages.NOTE_ON and e.pitch==62:on=at
            self.assertGreater(off,on)
            self.assertAlmostEqual((off-on)/960,.03,places=3)
