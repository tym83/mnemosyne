"""Audio-only performance invariants; synthesis evidence is measured in studio."""
import tempfile
from pathlib import Path
from unittest.mock import patch
import unittest
import numpy as np
from music21 import instrument,note,stream,spanner
from mnemosyne.music.live_performance import perform,profile,warp,vibrato_points,seat,prepare_patch,expression_points
from mnemosyne.music.schools.performance import sounding_events,write_midi
from mnemosyne.music.sample_sustain import prepare_region

class LivePerformanceTests(unittest.TestCase):
 def part(self,ins=instrument.Flute):
  p=stream.Part();p.insert(0,ins())
  for i in range(8):
   n=note.Note(60+i,quarterLength=1);n.volume.velocity=64;p.insert(i,n)
  return p
 def test_determinism_and_score_unchanged(self):
  p=self.part();before=list(sounding_events(p));a,log=perform(before,p,60,'symphony')
  self.assertEqual((a,log),perform(before,p,60,'symphony'))
  self.assertEqual(before,list(sounding_events(p)))
  self.assertGreater(np.std([x[3] for x in a]),2)
  self.assertGreater(np.std([x['timing_ms'] for x in log]),10)
 def test_rigid_and_feldman(self):
  p=self.part(instrument.Piano);ev=list(sounding_events(p))
  for school in ('reich','ustvolskaya','additive'):
   actual,_=perform(ev,p,60,school);self.assertEqual(actual,ev)
  actual,_=perform(ev,p,60,'feldman')
  self.assertLessEqual(max(x[3] for x in actual),33)
  self.assertLessEqual(np.ptp([x[3] for x in actual]),1)
 def test_monotone_clock_no_phrase_drift(self):
  times=[warp(t,profile('symphony')) for t in np.linspace(0,64,6401)]
  self.assertTrue(np.all(np.diff(times)>0))
  for t in range(0,65,8):self.assertAlmostEqual(warp(t,profile('symphony')),t)
 def test_winds_breathe(self):
  p=self.part();actual,log=perform([(0,20,(60,),64,None)],p,60,'symphony')
  self.assertGreater(len(actual),1);self.assertGreater(log[0]['breath_breaks'],0)
  self.assertLessEqual(max(x[1] for x in actual),6)
  self.assertTrue(all(b[0]-a[0]-a[1]>=.159 for a,b in zip(actual,actual[1:])))
 def test_slur_overlap_and_rest(self):
  p=self.part();ns=list(p.flatten().notes);p.insert(0,spanner.Slur(ns[0],ns[-1]))
  actual,_=perform(list(sounding_events(p,60)),p,60,'symphony')
  self.assertTrue(all(a[0]+a[1]>b[0] for a,b in zip(actual,actual[1:])))
  rest=[(0,1,(60,),64,None),(2,1,(62,),64,None)]
  actual,_=perform(rest,p,60,'symphony');self.assertLess(actual[0][0]+actual[0][1],actual[1][0])
 def test_vibrato_delay_depth(self):
  points=vibrato_points(0,3,60,base=.5)
  self.assertTrue(all(abs(p-.5)<1e-9 for t,p in points if t<=.45))
  late=[p for t,p in points if 1<t<2]
  self.assertAlmostEqual((max(late)-min(late))*100,24,delta=.15)
 def test_release_opcodes_untouched(self):
  zone={'sample':'release.wav','trigger':'release','opcodes':{'ampeg_release':'.02','rt_decay':'3','loop_mode':'one_shot'}}
  with patch('mnemosyne.music.sample_sustain.audio_info',return_value={'rate':8000,'seconds':1,'channels':1}):
   overrides,report=prepare_region(zone,{'release_seconds':.8,'sustained':True},Path('/unused'))
  self.assertEqual(overrides,{});self.assertEqual(report['sustain'],'recorded-release')
 def test_seating_delay(self):
  x=np.zeros((4410,2));x[0]=1
  y,report=seat(x,-.5,'brass',44100)
  self.assertEqual(np.count_nonzero(np.max(abs(y),axis=1)),3)
  self.assertGreater(y[0,0],y[0,1])
  self.assertEqual(len(report['early_reflections']),2)
 def test_xml_not_edited_by_midi_performance(self):
  score=stream.Score();score.insert(0,self.part())
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);score.write('musicxml',fp=d/'a.musicxml');a=(d/'a.musicxml').read_bytes()
   write_midi(score,d/'a.mid',60,performance='symphony')
   self.assertEqual(a,(d/'a.musicxml').read_bytes())
   self.assertTrue((d/'a.performance.json').exists())
 def test_phrase_expression_preserves_woven_curve(self):
  p=self.part();p.editorial.school_expression=[(0,.71),(4,.93),(8,.72)]
  before=list(p.editorial.school_expression)
  values=expression_points(p,60,'symphony')
  self.assertGreater(np.ptp([v for _,v in values]),10)
  self.assertEqual(p.editorial.school_expression,before)
  self.assertEqual(expression_points(p,60,'reich'),[(a,round(v*96)) for a,v in before])
 def test_held_tone_is_level_unless_the_plan_asks_for_swell(self):
  p=stream.Part();p.insert(0,instrument.Violin());p.insert(0,note.Note(67,quarterLength=6))
  piano=stream.Part();piano.insert(0,instrument.Piano());piano.insert(0,note.Note(67,quarterLength=6))
  # Without the device a bowed tone follows the same phrase envelope as the piano.
  self.assertEqual([v for _,v in expression_points(p,60,'symphony')],[v for _,v in expression_points(piano,60,'symphony')])
 def test_held_tone_opens_then_fades_into_release(self):
  p=stream.Part();p.insert(0,instrument.Violin());p.insert(0,note.Note(67,quarterLength=6))
  values=dict(expression_points(p,60,'symphony',held_swell=True))
  level=lambda t:values[min(values,key=lambda a:abs(a-t))]
  self.assertLess(level(0),level(2));self.assertLess(level(5.9),level(3))
  piano=stream.Part();piano.insert(0,instrument.Piano());piano.insert(0,note.Note(67,quarterLength=6))
  flat=dict(expression_points(piano,60,'symphony'))
  key=lambda v,t:v[min(v,key=lambda a:abs(a-t))]
  # Piano keeps the phrase envelope only; bowed tone also tapers per note.
  self.assertLess(level(5.9)/level(3),key(flat,5.9)/key(flat,3)-.2)
 def test_native_layers_and_release_survive_legato_adapter(self):
  from mnemosyne.music.native_bank import regions
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'sample.wav').touch();src=d/'a.sfz';dst=d/'b.sfz'
   src.write_text('<control> set_cc20=64\n<global> sample=sample.wav key=60 loop_start=100 loop_end=900\n'
                  '<region> lovel=1 hivel=63 seq_length=2 seq_position=1\n'
                  '<region> lovel=1 hivel=63 seq_length=2 seq_position=2\n'
                  '<region> lovel=64 hivel=127\n'
                  '<region> trigger=release rt_decay=3 loop_mode=one_shot\n')
   prepare_patch(src,dst,'woodwinds',legato=True)
   zones=regions(dst)
   self.assertEqual(sum(z['trigger']=='legato' for z in zones),3)
   self.assertEqual(sum(z['trigger']=='first' for z in zones),3)
   release=next(z for z in zones if z['trigger']=='release')
   self.assertEqual(release['opcodes']['rt_decay'],'3')
   self.assertNotIn('pitchlfo_depth',release['opcodes'])
   self.assertIn('set_cc20=64',dst.read_text())
 def test_inline_includes_expand_in_order_relative_to_root(self):
  from mnemosyne.music.native_bank import preprocess,regions
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);(d/'Data').mkdir();(d/'sample1.wav').touch();(d/'sample2.wav').touch()
   (d/'main.sfz').write_text('#include "Data/notes.txt"')
   (d/'Data/one.txt').write_text('#define $LAYER 1')
   (d/'Data/two.txt').write_text('#define $LAYER 2')
   (d/'Data/region.txt').write_text('<region> sample=sample$LAYER.wav key=60')
   (d/'Data/notes.txt').write_text('<group> #include "Data/one.txt" lovel=1 hivel=63 #include "Data/region.txt"\n<group> #include "Data/two.txt" lovel=64 hivel=127 #include "Data/region.txt"')
   self.assertNotIn('#include',preprocess(d/'main.sfz'))
   zones=regions(d/'main.sfz')
   self.assertEqual([(z['lovel'],z['hivel']) for z in zones],[(1,63),(64,127)])
   self.assertTrue(zones[1]['sample'].endswith('sample2.wav'))

class StudioAudioRegressionTests(unittest.TestCase):
 """Opt-in measured sfizz regression; fixtures rendered by measure28.py."""
 def test_engine_measurements(self):
  import os,json
  path=os.environ.get('MNEMO_LIVE_MEASUREMENTS')
  if not path:self.skipTest('Render studio fixtures and set MNEMO_LIVE_MEASUREMENTS')
  d=json.loads(Path(path).read_text())
  self.assertLess(d['recorded_release']['pre_noteoff_difference_dbfs'],-120)
  self.assertGreater(d['recorded_release']['post_noteoff_difference_dbfs'],-80)
  self.assertLess(d['piano_recorded_release']['pre_noteoff_difference_dbfs'],-120)
  self.assertGreater(d['piano_recorded_release']['post_noteoff_difference_dbfs'],-120)
  for boundary in d['slurs']:
   self.assertGreater(boundary['after']['minimum_relative_db'],-12)
   self.assertLess(boundary['after']['maximum_relative_db'],6)
  self.assertGreater(d['attack_bypass_engine']['suppression_db'],40)
  v=d['vibrato_engine']
  self.assertLess(v['early_peak_to_peak_cents'],.5)
  self.assertTrue(22<v['late_peak_to_peak_cents']<26)
  self.assertTrue(.45<v['first_over_2_cents_seconds']<.7)
