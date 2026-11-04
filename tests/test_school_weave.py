"""Authenticated school dynamics, notation invariants and series loss recovery."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import converter
from scheherazade.music.schools import SCHOOLS
from scheherazade.music.instrumentarium import REGISTRY, sample_patch, notation_instrument
from scheherazade.music.render import note_events
from scheherazade.weave import DecodeError, frames, fountain, payload, schools, surface
from scheherazade.weave.school_audit import plan_for


class SchoolWeaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = X25519PrivateKey.generate()
        plan = plan_for('serial')
        cls.score = SCHOOLS['serial'].compose(plan,plan['seed'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'score.musicxml'
            cls.score.write('musicxml',fp=path)
            cls.root = schools.prepare(surface.read(path),'serial')

    def test_minimum_and_note_invariants(self):
        self.assertGreaterEqual(schools.capacity(self.root),32)
        self.assertTrue(all(hasattr(m,'FREE_CHANNELS') for m in SCHOOLS.values()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'score.musicxml'
            woven = schools.encode(self.root,os.urandom(schools.capacity(self.root)))
            surface.write(woven,path)
            parsed = converter.parse(path).toSoundingPitch()
            self.assertEqual(note_events(parsed.stripTies()),note_events(self.score.stripTies()))
            self.assertEqual(schools.context(woven),schools.context(self.root))
        ids=[d.get('id') for d in self.root.iter('direction') if d.get('id','').startswith(schools.PREFIX)]
        self.assertEqual(len(ids),len(set(ids)))

    def test_series_and_tampering(self):
        content=os.urandom(256)
        env=payload.seal(content,self.key.public_key(),context=frames.DOMAIN)
        count=(len(env)+schools.capacity(self.root)-frames.OVERHEAD-1)//(schools.capacity(self.root)-frames.OVERHEAD)
        roots=[schools.weave_frame(self.root,env,i,self.key) for i in range(count)]
        decoded=[schools.read_frame(r,self.key) for r in roots]
        self.assertEqual(frames.assemble(decoded,self.key),content)
        for mutate in ('note','dynamic','offset','remove'):
            with self.subTest(mutate=mutate):
                root=deepcopy(roots[0])
                if mutate=='note':root.find('.//pitch/octave').text='9'
                elif mutate=='dynamic':
                    sound,opts=schools.slots(root)[0]
                    sound.set('dynamics',str(opts[(opts.index(float(sound.get('dynamics')))+1)%16]))
                else:
                    parent=next(m for m in root.iter('measure') if any(d.get('id','').startswith(schools.PREFIX) for d in m.findall('direction')))
                    d=next(d for d in parent.findall('direction') if d.get('id','').startswith(schools.PREFIX))
                    if mutate=='remove':parent.remove(d)
                    else:d.find('offset').text='99'
                with self.assertRaises(DecodeError):schools.read_frame(root,self.key)
        with self.assertRaises(DecodeError):schools.read_frame(roots[0],X25519PrivateKey.generate())
        with self.assertRaises(DecodeError):frames.assemble(decoded[:-1],self.key)

    def test_fountain_repair_only_and_work_binding(self):
        content=b'frame loss recovery through school music'
        env=payload.seal(content,self.key.public_key(),context=fountain.DOMAIN)
        enc=fountain.Encoder(env,schools.capacity(self.root)-12,self.key)
        decoded=[]
        for index in range(enc.k,2*enc.k+32):
            root=schools.weave_fountain(self.root,enc,index,self.key)
            decoded.append(schools.read_fountain(root,self.key))
        self.assertEqual(fountain.recover(decoded,self.key),content)
        root.find('.//pitch/octave').text='9'
        with self.assertRaises(DecodeError):schools.read_fountain(root,self.key)

    def test_performance_adapter_preserves_numeric_expression(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'score.musicxml'
            root = schools.encode(self.root,b'\0'*schools.capacity(self.root))
            surface.write(root,path)
            score = schools.performance_score(path)
            curves = schools.expression_curves(root)
            self.assertEqual(len(curves),len(score.parts))
            for part,curve in zip(score.parts,curves):
                self.assertEqual(part.editorial.school_expression,curve)
                self.assertTrue(all(0 < gain < 1 for at,gain in curve))
                self.assertEqual(curve,sorted(curve))
            # First serial onset is at zero; there must be no measure-offset drift.
            self.assertEqual(min(at for curve in curves for at,gain in curve),0)
            self.assertLess(max(at for curve in curves for at,gain in curve),216)
            from scheherazade.music.schools.performance import write_midi
            from music21 import midi
            target=Path(directory)/'score.mid'
            write_midi(score,target,72)
            parsed=midi.MidiFile();parsed.open(str(target));parsed.read();parsed.close()
            expression=[e for t in parsed.tracks for e in t.events
                        if e.type==midi.ChannelVoiceMessages.CONTROLLER_CHANGE and e.parameter1==11]
            self.assertEqual(len(expression),sum(map(len,curves)))

    def test_synthesis_realizes_expression(self):
        import wave
        import numpy as np
        from music21 import note, stream
        from scheherazade.music.schools.synthesis import render_synthesis
        score=stream.Score();part=stream.Part();part.append(note.Note('C4',quarterLength=1));score.insert(0,part)
        plan={'duration':1,'tempo':60,'seed':42,'school':'chance'}
        with tempfile.TemporaryDirectory() as directory:
            paths=[Path(directory)/'plain.wav',Path(directory)/'shaded.wav']
            render_synthesis(score,plan,paths[0])
            part.editorial.school_expression=[(0,.9),(1,.9)]
            render_synthesis(score,plan,paths[1])
            arrays=[]
            for path in paths:
                with wave.open(str(path),'rb') as file:
                    arrays.append(np.frombuffer(file.readframes(file.getnframes()),dtype='<i2').astype(float))
            self.assertGreater(np.max(np.abs(arrays[0])),100)
            self.assertLess(np.max(np.abs(arrays[1]-.9*arrays[0])),2)

    def test_invalid_surface_and_short_work(self):
        with self.assertRaises(ValueError):schools.prepare(self.root,'serial')
        with self.assertRaises(ValueError):schools.encode(self.root,b'\0')
        bad=deepcopy(self.root)
        sound,opts=schools.slots(bad)[0];sound.set('dynamics','nan')
        with self.assertRaises(DecodeError):schools.decode(bad)

    def test_voice_audio_status_and_choir(self):
        for name in ('soprano','alto','tenor','bass_voice'):
            self.assertFalse(REGISTRY[name]['samples']['audio_available'])
            self.assertTrue(REGISTRY[name]['samples']['notation_available'])
            notation_instrument(name)
            with self.assertRaises(ValueError):sample_patch(name,'sustain')
            self.assertTrue(sample_patch(name+'_choir','sustain'))


if __name__=='__main__':unittest.main()
