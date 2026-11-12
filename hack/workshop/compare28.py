"""Same-score 40 second auditions. Run detached in studio-0, not on a laptop."""
import argparse,json,math,subprocess,time,resource,hashlib
from pathlib import Path
import numpy as np
from music21 import converter,stream
from mnemosyne.music.orchestra_render import stem_score
from mnemosyne.music.native_bank import playback_patch,playback_source,regions,sha
from mnemosyne.music.instrumentarium import REGISTRY
from mnemosyne.music.schools.performance import write_midi,sounding_events
from mnemosyne.music.resonance import read_pedals,copy_slurs
from mnemosyne.music.live_performance import prepare_patch,seat
RATE=44100;ROOT=Path('/work/task28');OUT=ROOT/'compare';BANK=Path('/work/samples/instrumentarium')
SFIZZ='/work/sfizz-build/library/bin/sfizz_render'
VSCO={'flute':'FluteSusNV','oboe':'OboeSusNV','clarinet':'ClarinetSus','bassoon':'BassoonSus','horn':'FHornSus','trumpet':'TrumpetSus','trombone':'TromboneSus','tuba':'TubaSus','timpani':'Timpani','cymbals':'GM-StylePerc','harp':'Harp','violin_1_section':'ViolinEnsSusVib','violin_2_section':'ViolinEnsSusVib','viola_section':'ViolaEnsSusVib','cello_section':'CelloEnsSusVib','bass_section':'ContrabassSusVB','piano':'UprightPiano'}

def run(args,log):
 offset=log.stat().st_size if log.exists() else 0
 with log.open('a') as f:subprocess.run(list(map(str,args)),stdout=f,stderr=f,check=True)
 if str(args[0])==SFIZZ:
  with log.open() as f:f.seek(offset);output=f.read()
  if 'Parse error' in output or 'Cannot open file for reading' in output:raise RuntimeError(f'Incomplete SFZ load: {log}')

def pcm(path):
 return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-ar',str(RATE),'-ac','2','-f','f32le','-']),dtype='<f4').reshape(-1,2)

def sources():
 sym=Path('/work/gen/symphony-test-v2/mv1');piano=Path('/work/task27-v3/schools-v3/tintinnabuli')  # v3 score carries the pedal marks
 plan=json.loads((sym/'plan.json').read_text());ass=json.loads((sym/'orchestration.json').read_text())
 # First 40 seconds include sustained strings plus flute/oboe/clarinet/bassoon.
 yield 'symphony',sym,plan,ass['players']
 plan=json.loads((piano/'plan.json').read_text());score=converter.parse(piano/'score.musicxml').toSoundingPitch()
 players=[]
 for i,p in enumerate(score.parts):
  ev=[dict(at=a,duration=d,pitches=ps,velocity=v,glide=g,technique='sustain',gain_db=0.) for a,d,ps,v,g in sounding_events(p)]
  players.append(dict(id=f'piano-{i}',instrument='piano',pan=0.,events=ev))
 yield 'tintinnabuli',piano,plan,players

def patch_for(candidate,instrument,technique,dest):
 if candidate in ('sso','after-b','before') or candidate.startswith('after-b-'):
  playback_patch(BANK,instrument,technique,dest)
 elif candidate in ('vsco','vsco-live','after-a-b','salamander'):
  if instrument=='piano' and candidate in ('after-a-b','salamander'):
   playback_source(ROOT/'salamander'/'Salamander Grand Piano V3.sfz',instrument,technique,dest)
   return
  name=VSCO[instrument]
  if technique not in ('sustain','arco'):
   # Explicit native articulation mappings; never silently substitute sustain.
   options={('violin_1_section','pizzicato'):'ViolinEnsPizz',('violin_2_section','pizzicato'):'ViolinEnsPizz',('viola_section','pizzicato'):'ViolaEnsPizz',('cello_section','pizzicato'):'CelloEnsPizz',('bass_section','pizzicato'):'ContrabassPizz',('timpani','roll'):'TimpaniRolls'}
   if (instrument,technique) not in options:raise ValueError(f'Unmapped VSCO technique {instrument}/{technique}')
   name=options[instrument,technique]
  playback_source(ROOT/'vsco'/f'{name}.sfz',instrument,technique,dest)
 elif candidate=='vpo':
  mapping={'flute':'Woodwinds/flute-SOLO-sustain','oboe':'Woodwinds/oboe-SOLO-sustain','clarinet':'Woodwinds/clarinet-SOLO-sustain','bassoon':'Woodwinds/bassoon-SOLO-sustain','horn':'Brass/french-horn-SOLO-sustain','trumpet':'Brass/trumpet-SOLO-sustain','trombone':'Brass/trombone-SOLO-sustain','tuba':'Brass/tuba-SOLO-sustain','timpani':'Percussion/timpani-hit','cymbals':'Percussion/cymbals','harp':'Strings/harp-sustain','violin_1_section':'Strings/1st-violin-SEC-sustain','violin_2_section':'Strings/2nd-violin-SEC-sustain','viola_section':'Strings/viola-SEC-sustain','cello_section':'Strings/cello-SEC-sustain','bass_section':'Strings/bass-SEC-sustain'}
  if technique not in ('sustain','arco'):raise ValueError(f'Unmapped VPO technique {technique}')
  playback_source(ROOT/'vpo'/'Virtual-Playing-Orchestra3'/(mapping[instrument]+'.sfz'),instrument,technique,dest)
 else:raise ValueError(candidate)

def render(candidate):
 folder=OUT/candidate;folder.mkdir(parents=True,exist_ok=True)
 live=candidate in ('after-b','vsco-live','after-a-b') or candidate.startswith('after-b-')
 if 'noswell' in candidate:
  # Audition only: the same live layer without the held-tone swell.
  import mnemosyne.music.live_performance as lp
  base_profile=lp.profile
  lp.profile=lambda school:{**base_profile(school),'swell':0.}
 for name,source,plan,players in sources():
  if candidate=='salamander' and name=='symphony':continue
  if candidate.startswith('after-b-') and name!='symphony':continue
  if candidate=='vpo' and name=='tintinnabuli':
   (folder/'tintinnabuli-unavailable.json').write_text(json.dumps({'reason':'VPO has no piano; no substitution made'}));continue
  if (folder/f'{name}.json').exists():continue
  if (folder/f'{name}.mp3').exists():(folder/f'{name}.mp3').rename(folder/f'{name}.failed.mp3')
  start=time.monotonic();work=folder/(name+'-'+str(time.time_ns()));work.mkdir();log=work/'render.log'
  source_hash=sha(source/'score.musicxml');original=converter.parse(source/'score.musicxml').toSoundingPitch();read_pedals(source/'score.musicxml',original)
  total=48.;mix=np.zeros((round(total*RATE),2),dtype=np.float32);hall_send=np.zeros_like(mix);reports=[]
  for pi,player in enumerate(players):
   groups={}
   for e in player['events']:
    if e['at']*60/plan['tempo']>=40:continue
    e=dict(e);e['duration']=min(e['duration'],40*plan['tempo']/60-e['at'])
    groups.setdefault((e['technique'],e['gain_db']),[]).append(e)
   for gi,((technique,gain),events) in enumerate(groups.items()):
    base=work/f'{player["id"]}-{gi}';mid=base.with_suffix('.mid');wav=base.with_suffix('.wav');pat=base.with_suffix('.sfz')
    score=stem_score(events,player['instrument'],total*plan['tempo']/60)
    if pi<len(original.parts):
     copy_slurs(original.parts[pi],score.parts[0]);score.parts[0].editorial.sustain_pedal=[(a,v) for a,v in original.parts[pi].editorial.sustain_pedal if a<=40*plan['tempo']/60]
     if score.parts[0].editorial.sustain_pedal:score.parts[0].editorial.sustain_pedal.append((40*plan['tempo']/60,0))
    write_midi(score,mid,plan['tempo'],performance=plan['school'] if live else None,sample_vibrato=candidate!='musescore')
    if candidate=='musescore' or (candidate in ('after-b','before') and name=='tintinnabuli'):
     sf=ROOT/'musescore.sf3' if candidate=='musescore' else Path('/work/task27-v3/bank-v2/vsco-schools.sf2')
     run(['fluidsynth','-ni','-R','0','-C','0','-g','.6','-o','synth.cpu-cores=1','-F',wav,'-r',RATE,sf,mid],log)
     zone_report=[]
    else:
     cache=ROOT/'patches'/candidate;cache.mkdir(parents=True,exist_ok=True)
     pat=cache/f'{player["instrument"]}-{technique}.sfz'
     if not pat.exists():patch_for(candidate,player['instrument'],technique,pat)
     kind=REGISTRY[player['instrument']]['family']
     zone_report=[dict(trigger=z['trigger'],sample=z['sample'],lovel=z['lovel'],hivel=z['hivel'],rr=z['seq_length']) for z in regions(pat)]
     if live:
      livepat=base.with_suffix('.live.sfz');ordered=sorted(events,key=lambda e:e['at'])
      mono=all(len(e['pitches'])==1 for e in events) and all(a['at']+a['duration']<=b['at']+1e-7 for a,b in zip(ordered,ordered[1:]))
      prepare_patch(pat,livepat,kind,legato=mono);pat=livepat
      if 'norelease' in candidate and kind in ('strings','woodwinds','brass'):
       blocks=livepat.read_text().split('<region>')
       livepat.write_text(blocks[0]+''.join('<region>'+b for b in blocks[1:] if 'trigger=release' not in b))
     run([SFIZZ,'--sfz',pat,'--midi',mid,'--wav',wav,'--samplerate',RATE,'--use-eot'],log)
    data=pcm(wav);kind=REGISTRY[player['instrument']]['family']
    if not np.any(data):raise RuntimeError(f'Silent {base}')
    if live:data,seating=seat(data,player['pan'],kind,RATE)
    else:
     pan=player['pan'];data=data*np.array([math.sqrt(1-max(0,pan)),math.sqrt(1+min(0,pan))]);seating=None
    n=min(len(data),len(mix));mix[:n]+=data[:n]*10**(gain/20)
    hall_send[:n]+=data[:n]*10**(gain/20)*(seating['hall_send_gain'] if seating else 1.)
    reports.append(dict(player=player['id'],technique=technique,regions=zone_report,seating=seating))
  peak=float(abs(mix).max());mix*=.6/max(peak,1e-9);hall_send*=.6/max(peak,1e-9);mix.astype('<f4').tofile(work/'mix.f32')
  run(['ffmpeg','-v','error','-f','f32le','-ar',RATE,'-ac','2','-i',work/'mix.f32','-c:a','pcm_f32le',work/'dry.wav'],log)
  hall=ROOT/'hall-stereo.wav'
  if not hall.exists():run(['ffmpeg','-v','error','-i',BANK/'hall.wav','-af','pan=stereo|c0=0.7071*c0+0.5*c1+0.5*c2|c1=0.7071*c0+0.5*c1-0.5*c2','-ar',RATE,'-c:a','pcm_f32le',hall],log)
  graph="[0:a]asplit[d][s];[s][1:a]afir=dry=1:wet=1:irfmt=input[r];[d][r]amix=inputs=2:weights='1 0.25':normalize=0[out]"
  hall_send.astype('<f4').tofile(work/'send.f32')
  run(['ffmpeg','-v','error','-f','f32le','-ar',RATE,'-ac','2','-i',work/'send.f32','-c:a','pcm_f32le',work/'send.wav'],log)
  graph="[1:a][2:a]afir=dry=1:wet=1:irfmt=input[r];[0:a][r]amix=inputs=2:weights='1 0.25':normalize=0[out]"
  run(['ffmpeg','-v','error','-i',work/'dry.wav','-i',work/'send.wav','-i',hall,'-filter_complex',graph,'-map','[out]','-t','48','-c:a','pcm_f32le',work/'room.wav'],log)
  probe=subprocess.run(['ffmpeg','-i',str(work/'room.wav'),'-t','40','-af','loudnorm=I=-20:TP=-1.5:LRA=50:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
  loud=json.loads(probe.stderr[probe.stderr.rfind('{'):]);gain=min(-20-float(loud['input_i']),-1.5-float(loud['input_tp']))
  # Keep complete note releases in a separate tail audition; 40 s comparison has
  # an explicitly editorial edge fade, not evidence about note-release quality.
  for suffix,seconds in [('',40),('-with-tail',48)]:
   run(['ffmpeg','-v','error','-i',work/'room.wav','-af',f'volume={gain}dB,afade=t=out:st={seconds-.05}:d=0.05','-t',seconds,'-codec:a','libmp3lame','-q:a','2',folder/f'{name}{suffix}.mp3'],log)
  report=dict(candidate=candidate,excerpt=name,source=str(source),xml_sha256=source_hash,start_seconds=0,duration_seconds=40,wall_seconds=time.monotonic()-start,seconds_per_audio_minute=(time.monotonic()-start)*1.5,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,children_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,loudness=loud,gain_db=gain,stems=reports)
  (folder/f'{name}.json').write_text(json.dumps(report,indent=2));print(candidate,name,report['wall_seconds'],flush=True)
  assert source_hash==sha(source/'score.musicxml')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('candidate');args=ap.parse_args();render(args.candidate)
