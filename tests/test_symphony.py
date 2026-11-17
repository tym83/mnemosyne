"""Form, cyclic development, orchestration and published-surface recovery."""
from copy import deepcopy
import tempfile
import hashlib
from pathlib import Path
import unittest
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import converter, note, stream, tempo
from mnemosyne.music.symphony import (test_plan,validate,transform,movement,join_scores,FORMS,write_score)
from mnemosyne.music.instrumentarium import notation_instrument
from mnemosyne.music.schools.common import finish
from mnemosyne.weave import orchestral, DecodeError


class FormTests(unittest.TestCase):
    def setUp(self):self.plan=test_plan()

    def test_duration_and_proportions(self):
        self.assertEqual(validate(self.plan),1200)
        self.assertEqual([sum(s['bars'] for s in m['sections']) for m in self.plan['movements']],[96,112,140])

    def test_contract_rejections(self):
        for mutation in (lambda p:p.update(movements=p['movements'][:2]),
                         lambda p:p.update(concept=''),
                         lambda p:p['movements'][0].update(tempo=float('nan')),
                         lambda p:p['movements'][0]['sections'][0].update(bars=1.5),
                         lambda p:p['movements'][0]['sections'][0].update(role='coda'),
                         lambda p:p['movements'][0].update(schools=['unknown']),
                         lambda p:p['movements'][0]['sections'][0].update(tension=[-1,.5])):
            p=deepcopy(self.plan);mutation(p)
            with self.assertRaises(ValueError):validate(p)

    def test_transformations(self):
        theme={'pitches':[60,62,65,64],'durations':[1,1,2,4]};before=deepcopy(theme)
        self.assertEqual(transform(theme,'inversion')[0],[60,58,55,56])
        self.assertEqual(transform(theme,'augmentation')[1],[2,2,4,8])
        self.assertEqual(transform(theme,'retrograde')[0],[64,65,62,60])
        self.assertEqual(transform(theme,'fragmentation')[0],[60,62])
        self.assertEqual(transform(theme,'identity',5)[0],[65,67,70,69])
        self.assertEqual(theme,before)

    def test_all_forms_and_development_required(self):
        for form,roles in FORMS.items():
            p=deepcopy(self.plan);mv=p['movements'][0];mv['form']=form
            mv['sections']=[dict(mv['sections'][0],role=r,bars=8,transform='inversion') for r in roles]
            validate(p,study=True)
        for sec in p['movements'][0]['sections']:sec['transform']='identity'
        with self.assertRaisesRegex(ValueError,'development'):validate(p,study=True)

    def test_cyclic_material_required(self):
        self.plan['themes']['other']=deepcopy(self.plan['themes']['distance'])
        for sec in self.plan['movements'][1]['sections']:sec['theme']='other'
        with self.assertRaisesRegex(ValueError,'cyclic'):validate(self.plan)

    def test_small_realization(self):
        for mv in self.plan['movements']:
            for sec in mv['sections']:sec['bars']=8
        before=deepcopy(self.plan)
        score,op,assignment,analysis=movement(self.plan,0)
        self.assertAlmostEqual(float(score.highestTime)*60/op['tempo'],analysis['seconds'])
        self.assertTrue(analysis['returns'])
        self.assertEqual({s['role'] for s in analysis['sections']},set(FORMS['sonata']))
        self.assertTrue(any(r['development']=='complete return' for r in analysis['returns']))
        for section in analysis['sections']:self.assertTrue(section['usage'])
        self.assertEqual(before,self.plan)
        self.assertTrue(all(e['at']+e['duration']<=score.highestTime for p in assignment['players'] for e in p['events']))

    def test_all_form_realizations(self):
        for form, roles in FORMS.items():
            with self.subTest(form=form):
                p=deepcopy(self.plan);mv=p['movements'][0];mv['form']=form
                mv['sections']=[dict(mv['sections'][0],role=r,bars=8,
                    transform=['identity','inversion','fragmentation','reharmonisation'][i%4])
                    for i,r in enumerate(roles)]
                score,op,assignment,report=movement(p,0)
                self.assertEqual(float(score.highestTime),len(roles)*32)
                self.assertEqual(len(report['sections']),len(roles))
                self.assertTrue(any(r['development']=='complete return' for r in report['returns']))

    def test_orchestral_surface_roundtrip(self):
        for sec in self.plan['movements'][0]['sections']:sec['bars']=8
        score,_,_,_=movement(self.plan,0)
        scores=[deepcopy(score) for _ in range(4)]
        key=X25519PrivateKey.generate();data=b'fixture'
        orchestral.encode(scores,data,key.public_key())
        with tempfile.TemporaryDirectory() as folder:
            restored=[]
            for i,s in enumerate(scores):
                p=Path(folder)/f'{i}.musicxml';write_score(s,p)
                restored.append(converter.parse(p).toSoundingPitch())
            self.assertEqual(orchestral.decode(restored,key),data)
            combined=join_scores(restored,'Orchestral combined')
            path=Path(folder)/'combined.musicxml';write_score(combined,path)
            self.assertEqual(orchestral.decode([converter.parse(path).toSoundingPitch()],key),data)

    def test_notagen_requires_archived_material(self):
        self.plan['movements'][0]['schools']=['notagen']
        with self.assertRaisesRegex(ValueError,'NotaGen'):validate(self.plan)
        self.plan['notagen_material']={'pitches':[60,62], 'durations':[1,1],
            'source':{'kind':'test fixture, not a generated candidate'}}
        validate(self.plan)


class SurfaceTests(unittest.TestCase):
    def score(self,bars=240,bpm=60):
        score=stream.Score();score.atSoundingPitch=True
        part=stream.Part();part.insert(0,notation_instrument('harp'));part.insert(0,tempo.MetronomeMark(number=bpm))
        for _ in range(bars*4):
            part.append(note.Note(48,quarterLength=.5));part.append(note.Note(60,quarterLength=.5))
        score.insert(0,part);return finish(score,bars*4)

    def test_musicxml_and_combined_roundtrip(self):
        scores=[self.score(120),self.score(120,80)];key=X25519PrivateKey.generate();data=b'complete synthetic backup'
        report=orchestral.encode(scores,data,key.public_key())
        self.assertEqual(report['capacity_bytes'],120)
        self.assertEqual(hashlib.sha256(orchestral.envelope(scores)).hexdigest(),report['envelope_sha256'])
        self.assertEqual(hashlib.sha256(orchestral.context(scores)).hexdigest(),report['context_sha256'])
        self.assertEqual(orchestral.decode(scores,key),data)
        with tempfile.TemporaryDirectory() as folder:
            recovered=[]
            for i,s in enumerate(scores):
                path=Path(folder)/f'{i}.musicxml';s.write('musicxml',fp=path)
                recovered.append(converter.parse(path).toSoundingPitch())
            self.assertEqual(orchestral.decode(recovered,key),data)
            combined=join_scores(scores,'Test');path=Path(folder)/'combined.musicxml';combined.write('musicxml',fp=path)
            self.assertEqual(orchestral.decode([converter.parse(path).toSoundingPitch()],key),data)
        with self.assertRaises(DecodeError):orchestral.decode(scores,X25519PrivateKey.generate())
        scores[0].parts[0].flatten().notes[0].pitch.ps+=1
        with self.assertRaises(DecodeError):orchestral.decode(scores,key)

    def test_capacity_and_noncarrier_tampering(self):
        key=X25519PrivateKey.generate()
        with self.assertRaisesRegex(ValueError,'surface holds'):orchestral.encode([self.score(2)],b'x',key.public_key())
        score=self.score();part=stream.Part();part.insert(0,notation_instrument('flute'));part.append(note.Note(72,quarterLength=4));score.insert(0,part)
        orchestral.encode([score],b'x',key.public_key());part.notes[0].pitch.ps=73
        with self.assertRaises(DecodeError):orchestral.decode([score],key)


if __name__=='__main__':unittest.main()


class JoinTests(unittest.TestCase):
    def test_a_player_added_in_one_movement_rests_through_the_others(self):
        from music21 import meter, note, stream

        def movement(ids):
            score = stream.Score()
            for pid in ids:
                part = stream.Part()
                part.append(meter.TimeSignature('3/4'))
                for _ in range(2):
                    part.append(note.Note('C4', quarterLength=3))
                part = part.makeMeasures()
                part.id = part.partName = pid
                score.insert(0, part)
            return score
        joined = join_scores([movement(['timpani-1']), movement(['timpani-1', 'timpani-2'])], 'Two')
        self.assertEqual([p.id for p in joined.parts], ['timpani-1', 'timpani-2'])
        extra = joined.parts[1]
        self.assertEqual(len(extra.getElementsByClass('Measure')), 4)
        self.assertEqual(len(extra.flatten().notes), 2)
        self.assertEqual(float(extra.highestTime), float(joined.parts[0].highestTime))
