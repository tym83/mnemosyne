"""Native stereo SFZ stems -> orchestral seating -> measured hall -> static LUFS gain.

Heavy work is intended for studio pods. Every attempt and original stem survives.
There is no GM fallback and no channel-count ceiling on the audio path.
"""
from copy import deepcopy
import json
import math
import sys
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np
from music21 import converter, stream, spanner, metadata
from .instrumentarium import ROOT, REGISTRY, notation_instrument
from .native_bank import audit_patch, check_coverage, sha, LIBRARIES, playback_patch
from .render import run, note_events
from .schools.common import put
from .schools.performance import write_midi

RATE=44100
TAIL=4


def strip_creator(path):
    import xml.etree.ElementTree as ET
    tree=ET.parse(path)
    for parent in tree.findall('identification'):
        for node in list(parent.findall('creator')):
            if node.text=='Music21':parent.remove(node)
    tree.write(path,encoding='utf-8',xml_declaration=True)


def engrave(score,base,log):
    xml=base.with_suffix('.musicxml')
    export=deepcopy(score)
    for i,part in enumerate(export.parts):
        ins=part.recurse().getElementsByClass('Instrument').first()
        if ins.midiChannel != 9:
            channel=i%15;ins.midiChannel=channel if channel<9 else channel+1
    export.write('musicxml',fp=str(xml));strip_creator(xml)
    import xml.etree.ElementTree as ET
    tree=ET.parse(xml)
    for i,part in enumerate(tree.findall('./part-list/score-part')):
        for midi in part.findall('midi-instrument'):
            original=score.parts[i].recurse().getElementsByClass('Instrument').first()
            local=i%15
            midi.find('midi-channel').text=str(10 if original.midiChannel==9 else local+(1 if local<9 else 2))
            device=ET.Element('midi-device',{'id':midi.attrib['id'],'port':str(i//15+1)})
            part.insert(list(part).index(midi),device)
    tree.write(xml,encoding='utf-8',xml_declaration=True)
    recovered=converter.parse(xml).toSoundingPitch()
    if note_events(score.stripTies())!=note_events(recovered.stripTies()):
        raise ValueError(f'Written/sounding MusicXML mismatch: {base}')
    run(['musicxml2ly','-o',base.with_suffix('.ly'),xml],log)
    ly=base.with_suffix('.ly')
    if len(score.parts)>12:
        size,paper=(10,'a2') if len(score.parts)>28 else (12,'a3')
        with ly.open('a') as f:
            f.write(f'\n#(set-global-staff-size {size})\n\\paper {{ #(set-paper-size \"{paper}\") }}\n')
    run(['lilypond','-dno-point-and-click','-o',base,ly],log)


def stem_score(events,name,total):
    score=stream.Score();score.atSoundingPitch=True
    part=stream.Part();part.insert(0,notation_instrument(name));score.insert(0,part)
    for event in events:
        at=event['at'];duration=event['duration'];pitches=event['pitches']
        if event.get('glide'):
            split,delta=event['glide']
            a=put(part,at,split,pitches)
            b=put(part,at+split,duration-split,tuple(p+delta for p in pitches))
            a.volume.velocity=b.volume.velocity=event['velocity']
            part.insert(at,spanner.Glissando(a,b,lineType='solid'))
        else:
            n=put(part,at,duration,pitches);n.volume.velocity=event['velocity']
    if part.highestTime<total:put(part,part.highestTime,total-part.highestTime,None)
    return score


def render_orchestra(score,plan,assignment,destination,bank,sfizz='/work/sfizz-build/library/bin/sfizz_render'):
    destination=Path(destination);bank=Path(bank)
    destination.mkdir(parents=True,exist_ok=True)
    if (destination/'render.json').exists():raise FileExistsError(destination)
    (destination/'.drafts').mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='attempt-',dir=destination/'.drafts'))
    log=work/'render.log'
    (work/'parts').mkdir();(work/'stems').mkdir();(work/'licenses').mkdir();(work/'patches').mkdir()
    for name,value in [('plan',plan),('orchestration',assignment)]:
        (work/f'{name}.json').write_text(json.dumps(value,indent=2))
    patches={};libraries=set();sample_files={}
    # Preflight everything before engraving or rendering. No missing-key silence.
    for player in assignment['players']:
        for event in player['events']:
            key=(player['instrument'],event['technique'])
            if key not in patches:
                patches[key]=audit_patch(bank,*key);libraries.add(patches[key]['library'])
                patches[key]['playback_file']=f'patches/{key[0]}-{key[1]}.sfz'
                playback_patch(bank,*key,work/patches[key]['playback_file'])
            for pitch in event['pitches']:check_coverage(patches[key],pitch,event['velocity'])
    for patch in patches.values():
        for zone in patch['regions']:
            path=Path(zone['sample'])
            if str(path) not in sample_files:sample_files[str(path)]=sha(path)
    engrave(score,work/'score',log)
    for part,player in zip(score.parts,assignment['players'],strict=True):
        # A divided section has one part per divided group; each musician gets
        # a copy of their group's part, rather than an impossible full divisi.
        single=stream.Score();single.atSoundingPitch=True
        single.metadata=metadata.Metadata(title=plan.get('title','')+' — '+player['id'])
        single.insert(0,deepcopy(part))
        # Export directly from sounding pitch: an extra written/sounding
        # transpose round trip in music21 can erase half-sharp accidentals.
        base=work/'parts'/player['id'];engrave(single,base,log)
        copies=player['players']
        for number in range(1,copies+1):
            shutil.copy2(base.with_suffix('.pdf'),base.with_name(base.name+f'-player-{number}').with_suffix('.pdf'))
    write_midi(score,work/'score.mid',plan['tempo'])
    samples=round((plan['duration']+TAIL)*RATE)
    mix=np.zeros((samples,2),dtype=np.float32)
    stems=[]
    for player in assignment['players']:
        groups={}
        for e in player['events']:groups.setdefault((e['technique'],e['gain_db']),[]).append(e)
        for index,((technique,gain),events) in enumerate(sorted(groups.items())):
            base=work/'stems'/f'{player["id"]}-{index}'
            midi=base.with_suffix('.mid');wav=base.with_suffix('.wav')
            one=stem_score(events,player['instrument'],(plan['duration']+TAIL)*plan['tempo']/60)
            write_midi(one,midi,plan['tempo'])
            patch=patches[(player['instrument'],technique)]
            normalized=work/patch['playback_file']
            run([sfizz,'--sfz',normalized,'--midi',midi,
                 '--wav',wav,'--samplerate',str(RATE),'--use-eot'],log)
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(wav),'-ar',str(RATE),'-ac','2','-f','f32le','-'])
            data=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
            if not len(data) or float(np.max(np.abs(data)))<1e-8:raise ValueError(f'Silent stem: {base}')
            pan=player['pan']
            gains=np.array([math.sqrt(1-max(0,pan)),math.sqrt(1+min(0,pan))])*10**(gain/20)
            n=min(len(data),samples);mix[:n]+=data[:n]*gains
            stems.append({'player':player['id'],'technique':technique,'gain_db':gain,'pan':pan,
                          'wav_sha256':sha(wav),'peak':float(np.max(np.abs(data)))})
    # Float intermediate keeps headroom; normalize only after the complete mix.
    raw_peak=float(np.max(np.abs(mix)));raw_rms=float(np.sqrt(np.mean(mix**2)))
    if raw_rms<1e-12:raise ValueError('Silent orchestral mix')
    pregain=min(.8/max(raw_peak,1e-12),.1/raw_rms)
    raw=work/'mix.f32';(mix*pregain).astype('<f4').tofile(raw)
    run(['ffmpeg','-nostdin','-v','warning','-f','f32le','-ar',RATE,'-ac',2,'-i',raw,
         '-c:a','pcm_f32le',work/'dry.wav'],log)
    run(['ffmpeg','-nostdin','-v','warning','-i',bank/'hall.wav','-af',
         'pan=stereo|c0=0.7071*c0+0.5*c1+0.5*c2|c1=0.7071*c0+0.5*c1-0.5*c2',
         '-ar',RATE,'-c:a','pcm_f32le',work/'hall-stereo.wav'],log)
    graph="[0:a]asplit[d][s];[s][1:a]afir=dry=1:wet=1:irfmt=input[r];[d][r]amix=inputs=2:weights='1 0.25':normalize=0[out]"
    run(['ffmpeg','-nostdin','-v','warning','-i',work/'dry.wav','-i',work/'hall-stereo.wav',
         '-filter_complex',graph,'-map','[out]','-t',plan['duration']+TAIL,'-c:a','pcm_f32le',work/'hall-mix.wav'],log)
    probe=subprocess.run(['ffmpeg','-nostdin','-i',str(work/'hall-mix.wav'),'-af',
                          'loudnorm=I=-20:TP=-1.5:LRA=50:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    measured=json.loads(probe.stderr[probe.stderr.rfind('{'):])
    integrated=float(measured['input_i']);peak=float(measured['input_tp'])
    if not math.isfinite(integrated) or not math.isfinite(peak):raise ValueError('Invalid loudness/silent mix')
    gain=min(-20-integrated,-1.5-peak)
    run(['ffmpeg','-nostdin','-v','warning','-i',work/'hall-mix.wav','-af',f'volume={gain}dB',
         '-codec:a','libmp3lame','-q:a','2',work/'score.mp3'],log)
    audio=subprocess.check_output(['ffmpeg','-v','error','-i',str(work/'score.mp3'),'-ac','2','-ar',str(RATE),'-f','f32le','-'])
    data=np.frombuffer(audio,dtype='<f4').reshape(-1,2)
    peak_after=float(np.max(np.abs(data)))
    if peak_after>=1 or abs(len(data)/RATE-plan['duration']-TAIL)>.15:raise ValueError('Audio peak/duration validation failed')
    analysis={'score_seconds':plan['duration'],'tail_seconds':TAIL,'audio_seconds':len(data)/RATE,
              'peak':peak_after,'rms':float(np.sqrt(np.mean(data**2))), 'channels':2,
              'raw_rms':raw_rms,'pregain':pregain,
              'loudness':{'measured':measured,'target_lufs':-20,'constant_gain_db':gain,
                          'estimated_output_lufs':integrated+gain,'peak_limited':gain< -20-integrated},'stems':stems}
    (work/'analysis.json').write_text(json.dumps(analysis,indent=2))
    provenance={'libraries':{name:LIBRARIES[name] for name in sorted(libraries)},
                'patches':list(patches.values()),'sample_hashes':sample_files,
                'hall':{**LIBRARIES['openair_jack_lyons'],'sha256':sha(bank/'hall.wav')},
                'sfizz_binary_sha256':sha(sfizz)}
    (work/'samples.json').write_text(json.dumps(provenance,indent=2))
    for name in libraries:
        for file in LIBRARIES[name]['license_files']:
            shutil.copy2(bank/name/file,work/'licenses'/f'{name}-{Path(file).name}')
    (work/'licenses'/'hall.json').write_text(json.dumps(LIBRARIES['openair_jack_lyons'],indent=2))
    for file in ('instruments.yaml','ensembles.yaml','sample_libraries.yaml'):
        shutil.copy2(ROOT/file,work/file)
    sources={str(p.relative_to(ROOT)):p.read_text() for p in list(ROOT.glob('*.py'))+list((ROOT/'schools').glob('*.py'))}
    (work/'sources.json').write_text(json.dumps(sources,indent=2))
    files=[p for p in work.rglob('*') if p.is_file() and ('stems' not in p.relative_to(work).parts or p.suffix=='.sfz') and p.suffix not in ('.wav','.f32')]
    artifacts={str(p.relative_to(work)):sha(p) for p in files}
    for source in files:
        target=destination/source.relative_to(work);target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(source,target)
    (destination/'render.json').write_text(json.dumps({'renderer':'native-sfz-1','python':sys.version,
        'music21':__import__('music21').__version__,'numpy':np.__version__,
        'sfizz':'1.2.3','draft':str(work),'artifacts':artifacts},indent=2))
    print(f'Rendered {destination}: {len(stems)} stereo stems, peak {peak_after:.3f}, {integrated+gain:.1f} LUFS',flush=True)
