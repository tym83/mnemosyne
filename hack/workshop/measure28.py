"""Audio ablations, not assertions about perceived quality. Run in studio."""
from pathlib import Path
import json,math,subprocess
import numpy as np
from scipy.signal import hilbert
from music21 import instrument,note,spanner,stream
from mnemosyne.music.native_bank import playback_patch,regions
from mnemosyne.music.live_performance import prepare_patch
from mnemosyne.music.schools.performance import write_midi
from compare28 import ROOT,BANK,SFIZZ,RATE,run,pcm
D=ROOT/'measurements';D.mkdir(exist_ok=True);log=D/'render.log';report={}

def synth(patch,score,name):
 mid=D/f'{name}.mid';wav=D/f'{name}.wav';write_midi(score,mid,60)
 run([SFIZZ,'--sfz',patch,'--midi',mid,'--wav',wav,'--samplerate',RATE,'--use-eot'],log)
 return pcm(wav).mean(axis=1)
def score(pitches,lengths,slur=False,ins=instrument.Flute):
 s=stream.Score();p=stream.Part();p.insert(0,ins());s.insert(0,p)
 for pitch,length in zip(pitches,lengths):
  n=note.Note(pitch,quarterLength=length);n.volume.velocity=80;p.append(n)
 if slur:p.insert(0,spanner.Slur(*list(p.notes)))
 p.append(note.Rest(quarterLength=3));return s

def db(x):return float(20*np.log10(np.sqrt(np.mean(np.asarray(x,dtype=float)**2))+1e-12))
# Native timpani-roll release tails: removing release zones is the control.
pat=D/'timpani.sfz';playback_patch(BANK,'timpani','sustain',pat)
z=regions(pat);ablate=D/'timpani-no-release.sfz'
ablate.write_text('\n'.join('<region>\n'+'\n'.join(f'{k}={v}' for k,v in {**a['opcodes'],'sample':a['sample']}.items()) for a in z if a['trigger'] not in ('release','release_key')))
s=score([60],[2],ins=instrument.Timpani)
a=synth(pat,s,'release');b=synth(ablate,s,'release-ablated');n=min(len(a),len(b));delta=a[:n]-b[:n]
report['recorded_release']={'release_regions':sum(a['trigger'] in ('release','release_key') for a in z),'pre_noteoff_difference_dbfs':db(delta[:RATE*2]),'post_noteoff_difference_dbfs':db(delta[RATE*2:RATE*3]),'test_key':60,'noteoff_seconds':2}
# Actual flute slur: same MIDI, original attack vs loop-entry crossfade.
pat=D/'flute.sfz';playback_patch(BANK,'flute','sustain',pat);live=D/'flute-live.sfz';prepare_patch(pat,live,'woodwinds',legato=True)
s=score([72,74,76],[1,1,1],slur=True)
a=synth(pat,s,'slur-before');b=synth(live,s,'slur-after')
report['slurs']=[]
for t in (1,2):
 def boundary(x):
  windows=[db(x[round((t+d)*RATE):round((t+d+.01)*RATE)]) for d in np.arange(-.12,.13,.01)]
  ref=float(np.median(windows[:8]+windows[-8:]));return {'minimum_relative_db':min(windows)-ref,'maximum_relative_db':max(windows)-ref,'windows_dbfs':windows}
 report['slurs'].append({'seconds':t,'before':boundary(a),'after':boundary(b)})
# A known stationary source makes pitch deviation measurable without confusing
# existing sampled vibrato with modulation. This proves the sfizz LFO path only.
import wave
x=(np.sin(2*np.pi*440*np.arange(RATE*4)/RATE)*12000).astype('<i2')
with wave.open(str(D/'tone.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(x.tobytes())
pat=D/'tone.sfz';pat.write_text(f'<region> sample={D/"tone.wav"} key=69 loop_mode=loop_continuous loop_start=44100 loop_end=88199 ampeg_release=.2')
live=D/'tone-live.sfz';prepare_patch(pat,live,'woodwinds')
a=synth(live,score([69],[3]),'vibrato')
# Interpolated positive zero crossings, averaged over ten periods. This avoids
# Hilbert edge artefacts and 10 ms windows containing non-integer cycle counts.
y=a[:3*RATE]
indices=np.flatnonzero((y[:-1]<=0)&(y[1:]>0))
crossings=(indices-y[indices]/(y[indices+1]-y[indices]))/RATE
cents=[]
for i in range(len(crossings)-10):
 t=(crossings[i]+crossings[i+10])/2
 frequency=10/(crossings[i+10]-crossings[i])
 if .05<t<2.9:cents.append((float(t),1200*math.log2(frequency/440)))
early=[c for t,c in cents if .1<t<.4];late=[c for t,c in cents if 1<t<2.8]
report['vibrato_engine']={'early_peak_to_peak_cents':max(early)-min(early),'late_peak_to_peak_cents':max(late)-min(late),'first_over_2_cents_seconds':next((t for t,c in cents if t>.1 and abs(c)>2),None),'requested_delay_seconds':.45,'requested_depth_cents':12,'scope':'stationary calibration sample through actual sfizz; not natural sample vibrato'}
# Release ablation on the actual piano candidate, preserving SFZ controls.
from mnemosyne.music.native_bank import playback_source
import re
pat=D/'salamander.sfz';playback_source(ROOT/'salamander'/'Salamander Grand Piano V3.sfz','piano','sustain',pat)
zones=iter(regions(pat));count=[0]
def remove_release(match):
 z=next(zones)
 if z['trigger'] in ('release','release_key'):
  count[0]+=1;return ''
 return match[0]
ablated=D/'salamander-no-release.sfz';ablated.write_text(re.sub(r'<region>[^<]*',remove_release,pat.read_text()))
s=score([60],[2],ins=instrument.Piano)
a=synth(pat,s,'piano-release');b=synth(ablated,s,'piano-release-ablated');n=min(len(a),len(b));delta=a[:n]-b[:n]
report['piano_recorded_release']={'release_regions':count[0],'pre_noteoff_difference_dbfs':db(delta[:RATE*2]),'post_noteoff_difference_dbfs':db(delta[RATE*2:RATE*3]),'test_key':60}
# Inject an identifiable broadband attack in a calibration sample. Its absence
# on the second slurred note proves that fallback bypasses, not merely softens,
# the sample attack. The actual flute boundary measurements remain above.
from scipy.signal import butter,sosfilt
signal=np.sin(2*np.pi*440*np.arange(RATE*4)/RATE)*.2
signal[:4410]+=np.random.default_rng(28).normal(0,.2,4410)
with wave.open(str(D/'attack-tone.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes((signal*30000).astype('<i2').tobytes())
pat=D/'attack-tone.sfz';pat.write_text(f'<region> sample={D/"attack-tone.wav"} lokey=60 hikey=84 pitch_keycenter=69 loop_mode=loop_continuous loop_start=44100 loop_end=88199 ampeg_release=.2')
live=D/'attack-tone-live.sfz';prepare_patch(pat,live,'woodwinds',legato=True)
s=score([69,71],[1,1],slur=True)
a=synth(pat,s,'attack-before');b=synth(live,s,'attack-after')
flt=butter(4,3000,fs=RATE,btype='highpass',output='sos')
before=db(sosfilt(flt,a)[RATE+441:RATE+4410]);after=db(sosfilt(flt,b)[RATE+441:RATE+4410])
report['attack_bypass_engine']={'attack_band_before_dbfs':before,'attack_band_after_dbfs':after,'suppression_db':before-after,'scope':'known attack marker through sfizz; actual flute continuity measured separately'}
(D/'measurements.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
