"""Concept-first cyclic form engine. Durations are bars of 4/4, pitches sounding.

School grammars supply material reservoirs, not preassembled movements. Formal
sections develop those reservoirs and shared themes; all decisions are archived.
Run heavy composition/engraving/rendering in a studio pod, never via an artist.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
from music21 import converter, dynamics, expressions, metadata, stream
from .instrumentarium import REGISTRY
from .orchestration import Event, Line, orchestrate
from .schools import SCHOOLS

# The same bounded local touch freedom as the school reservoirs.
FREE_CHANNELS = {'period_quarters': 0.5, 'levels': 16,
                 'step_percent': 0.25, 'max_deviation_percent': 1.875}

FORMS = {
    'sonata': ['primary','transition','secondary','development','retransition','recapitulation','coda'],
    'scherzo-trio': ['scherzo','trio','scherzo_return','coda'],
    'variations': ['theme','variation','variation','variation','coda'],
    'passacaglia': ['ground','variation','variation','climax','coda'],
    'rondo': ['refrain','episode','refrain','episode','refrain','coda'],
    'through-composed': ['opening','growth','transformation','climax','dissolution'],
    'arch': ['A','B','C','B_return','A_return'],
    'moment': ['moment','moment','moment','moment'],
}
TRANSFORMS = {'identity','inversion','augmentation','diminution','retrograde','fragmentation','reharmonisation'}
# Full classical orchestra; section samples represent the stated real players.
ORCHESTRA = ([{'instrument':n,'count':c} for n,c in
              [('flute',2),('oboe',2),('clarinet',2),('bassoon',2),('horn',4),
               ('trumpet',2),('trombone',2),('tuba',1),('timpani',1),('cymbals',1),('harp',1)]]+
             [{'instrument':n,'players':c} for n,c in [('violin_1_section',16),('violin_2_section',14),
              ('viola_section',12),('cello_section',10),('bass_section',8)]])


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def validate(plan, *, study=False):
    from .instrumentarium import audio_ensemble
    players = audio_ensemble(plan.get('orchestra', ORCHESTRA))
    # movement() writes explicitly instrument-bound lines; a reduced orchestra
    # cannot realize this grammar even when all its individual samples exist.
    from collections import Counter
    available = Counter(p.instrument for p in players)
    required = Counter(p.instrument for p in audio_ensemble(ORCHESTRA))
    if required - available:
        raise ValueError('symphony grammar requires at least its default orchestra slots: '
                         + str(dict(required - available)))
    if plan.get('version')!=1 or not plan.get('concept') or not plan.get('method'):
        raise ValueError('version 1, concept and method required')
    mvs=plan.get('movements',[])
    if not 3<=len(mvs)<=5:raise ValueError('a symphony has 3–5 movements')
    themes=plan.get('themes',{})
    if not themes:raise ValueError('cyclic themes required')
    for theme in themes.values():
        ps,ds=theme.get('pitches',[]),theme.get('durations',[])
        if len(ps)<2 or len(ps)!=len(ds) or any(not finite(p) or not 0<=p<=127 for p in ps):
            raise ValueError('invalid theme pitches')
        if any(not finite(d) or d<=0 or d*4!=int(d*4) for d in ds):raise ValueError('invalid theme rhythm')
        if not theme.get('source'):raise ValueError('theme provenance required')
    heard=[]
    for mv in mvs:
        if not finite(mv.get('tempo')) or not 30<=mv['tempo']<=240:raise ValueError('invalid tempo')
        if mv.get('form') not in FORMS or not mv.get('character'):raise ValueError('form/character required')
        secs=mv.get('sections',[])
        if [s.get('role') for s in secs]!=FORMS[mv['form']]:raise ValueError('section order does not realize form')
        if not finite(mv.get('centre')) or not 0<=mv['centre']<=127:raise ValueError('invalid centre')
        used=set()
        for sec in secs:
            if type(sec.get('bars')) is not int or sec['bars']<4:raise ValueError('section needs >=4 whole bars')
            if sec.get('theme') not in themes:raise ValueError('unknown theme')
            used.add(sec['theme'])
            if sec.get('transform') not in TRANSFORMS:raise ValueError('unknown transformation')
            curve=sec.get('tension',[])
            if len(curve)!=2 or any(not finite(x) or not 0<=x<=1 for x in curve):raise ValueError('invalid tension curve')
            if not finite(sec.get('shift',0)):raise ValueError('invalid centre shift')
            styles=sec.get('schools',mv.get('schools',[]))
            if not styles or any(s not in {*SCHOOLS,'notagen'} for s in styles):raise ValueError('unknown/empty school mixture')
            if 'notagen' in styles and not plan.get('notagen_material',{}).get('source'):
                raise ValueError('NotaGen requires selected, archived material')
        if not any(s['transform']!='identity' for s in secs):raise ValueError('movement needs development')
        heard.append(used)
    if not set.intersection(*heard):raise ValueError('one cyclic theme must return in every movement')
    seconds=sum(sum(s['bars'] for s in m['sections'])*240/m['tempo'] for m in mvs)
    if not study and not 1200<=seconds<=2700:raise ValueError('symphony must last 20–45 minutes')
    return seconds


def transform(theme, operation, shift=0):
    ps=list(theme['pitches']);ds=list(theme['durations'])
    if operation not in TRANSFORMS:raise ValueError(operation)
    if operation=='inversion':ps=[2*ps[0]-p for p in ps]
    elif operation=='retrograde':ps.reverse();ds.reverse()
    elif operation=='augmentation':ds=[d*2 for d in ds]
    elif operation=='diminution':ds=[d/2 for d in ds]
    elif operation=='fragmentation':ps=ps[:max(2,len(ps)//2)];ds=ds[:len(ps)]
    return [p+shift for p in ps],ds


def school_material(name, centre, seed, settings=None):
    """Preserve the complete small source study and extract its sounding attacks."""
    plan={'school':name,'title':name+' material reservoir','ensemble':'string_quartet',
          'duration':32,'tempo':60,'tonic':centre,'centre':centre,'fundamental':centre-24,
          'form':[{'duration':32,'character':'flowing','density':.6,'register':[48,84]}]}
    plan.update(settings or {})
    score=SCHOOLS[name].compose(plan,seed)
    events=sorted((float(n.getOffsetInHierarchy(score)),float(n.quarterLength),p.ps)
                  for part in score.parts for n in part.recurse().notes for p in n.pitches)
    if not events:raise ValueError('empty school material')
    return {'plan':plan,'seed':seed,'events':events}


def selected_theme(directory, movement, curve, opening=None):
    """NotaGen alternative: select/analyze candidates, keep every critic result."""
    from . import select, analyze
    candidates=select._analyse_dir(Path(directory))
    for c in candidates:
        if 'features' in c:c['score']=select.score_movement(c['features'],movement,curve,opening)
    valid=[c for c in candidates if 'score' in c]
    if not valid:raise ValueError('no valid NotaGen candidates')
    chosen=max(valid,key=lambda c:c['score']['total'])
    source=Path(directory)/chosen['file']
    score=converter.parse(analyze.to_musicxml(source)).toSoundingPitch()
    ns=list(score.parts[0].flatten().notes)[:8]
    return {'pitches':[n.pitches[-1].ps for n in ns], 'durations':[float(n.quarterLength) for n in ns],
            'source':{'kind':'notagen','chosen':chosen['file'],'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                      'source_abc':source.read_text(),'selection':candidates}}


def fit(pitch, instrument):
    spec=REGISTRY[instrument];lo,hi=spec['comfortable']
    technique='arco' if spec['family']=='strings' else 'sustain'
    zones=spec['samples'].get('key_ranges',{}).get(technique,[[lo,hi]])
    options=[pitch+12*k for k in range(-10,11) if spec['range'][0]<=pitch+12*k<=spec['range'][1] and
             any(a<=round(pitch+12*k)<=b for a,b in zones)]
    if not options:raise ValueError(f'no comfortable sampled octave: {instrument}, {pitch}')
    return min(options,key=lambda p:(not lo<=p<=hi,abs(p-pitch)))


def movement(plan, index):
    mv=plan['movements'][index];bpm=mv['tempo'];bars=sum(s['bars'] for s in mv['sections'])
    op={'title':f"{plan['title']} — {index+1}. {mv['title']}",'ensemble':plan.get('orchestra',ORCHESTRA),
        'tempo':bpm,'duration':bars*240/bpm,'school':'symphony','audio_profile':'native_sfz'}
    buckets={};returns=[];sections=[];sources={};start=0
    def add(name,role,at,dur,pitch,vel):
        buckets.setdefault((name,role),[]).append(Event(at,dur,(fit(pitch,name),),vel))
    melodic=['violin_1_section','oboe','horn','clarinet','cello_section','flute']
    for si,sec in enumerate(mv['sections']):
        end=start+sec['bars']*4;length=end-start
        schools=sec.get('schools',mv.get('schools',[]))
        for school in schools:
            if school not in sources:
                if school=='notagen':
                    material=plan['notagen_material'];cursor=0;events=[]
                    for p,d in zip(material['pitches'],material['durations'],strict=True):
                        events.append((cursor,d,p));cursor+=d
                    sources[school]={'events':events,'source':material['source']}
                else:
                    sources[school]=school_material(school,mv['centre'],plan['seed']+index,
                                                   plan.get('school_settings',{}).get(school))
        theme=plan['themes'][sec['theme']]
        shift=mv['centre']-theme['pitches'][0]+sec.get('shift',0)
        ps,ds=transform(theme,sec['transform'],shift)
        target=melodic[(si+index*2)%len(melodic)]
        # Complete theme returns alternate with increasingly fragmented sequential
        # development. The last two bars prepare the next section's pitch centre.
        at=start;phrase=0
        while at<end-8:
            developing=phrase%3!=0
            local_ps,local_ds=(ps,ds)
            if developing:
                local_ps,local_ds=transform({'pitches':ps,'durations':ds},
                    'fragmentation' if phrase%2 else 'inversion', [0,2,-2,5][phrase%4])
            onset=at;actual=[]
            for p,d in zip(local_ps,local_ds):
                if at+d>end-8:break
                t=(at-start)/length;v=round(40+65*(sec['tension'][0]*(1-t)+sec['tension'][1]*t))
                add(target,'melody',at,d*.75,p,v);actual.append([at,d*.75,fit(p,target)]);at+=d
            if not actual:break
            returns.append({'theme':sec['theme'],'section':si+1,'at_quarters':onset,
                'at_seconds':onset*60/bpm,'instrument':target,'transformation':sec['transform'],
                'development':('fragmentation' if phrase%2 else 'inversion') if developing else
                    ('complete return' if len(actual)==len(local_ps) else 'truncated return'),
                'sequence_semitones':[0,2,-2,5][phrase%4] if developing else 0,
                'events':actual})
            at+=4 if sec['tension'][1]<.6 else 2;phrase+=1
        for bar in range(sec['bars']):
            a=start+bar*4;t=bar/max(1,sec['bars']-1)
            tension=sec['tension'][0]*(1-t)+sec['tension'][1]*t;vel=round(36+64*tension)
            # Harmonic rhythm accelerates in development. Reharmonisation changes
            # roots under the retained contour, never just changes a label.
            root=mv['centre']+sec.get('shift',0)+[0,5,3,7][(bar//(2 if tension>.6 else 4))%4]
            if sec['transform']=='reharmonisation':root += [0,-3,2,5][bar%4]
            if sec['role'] in ('ground','variation') and mv['form']=='passacaglia':
                root=mv['centre']+[0,-2,-4,-5][bar%4]
            if bar>=sec['bars']-2:
                nextsec=mv['sections'][min(si+1,len(mv['sections'])-1)]
                root=mv['centre']+nextsec.get('shift',0)+(7 if bar==sec['bars']-2 else 0)
            # Harp is the explicit surface voice: quiet octave figuration.
            low=48+int(root)%12
            for beat in range(4):
                add('harp','figuration',a+beat,.5,low,max(30,vel-20))
                add('harp','figuration',a+beat+.5,.5,low+12,max(30,vel-20))
            add('bass_section','bass',a,3.5,root-24,vel)
            if target!='cello_section':add('cello_section','counter_line',a+1,2.5,root-12+7,vel-5)
            add('viola_section','harmony_pad',a,3.5,root+3,vel-8)
            add('violin_2_section','harmony_pad',a+.5,3,root+7,vel-8)
            if target!='violin_1_section' and tension>.45:
                add('violin_1_section','counter_line',a+2,1.5,root+12,vel-8)
            school=schools[bar%len(schools)];ev=sources[school]['events']
            p=ev[(bar*3+si)%len(ev)][2]
            wood=['flute','clarinet','oboe','bassoon'][bar%4]
            if wood!=target:
                add(wood,'counter_line',a+1,1 if tension>.6 else 2,p,vel-4)
                if tension>.78 and wood!='bassoon':add(wood,'counter_line',a+1,1,p+7,vel-8)
            if tension>.55:
                for name,interval in [('horn',7),('bassoon',-12)]:
                    if name!=target:
                        add(name,'harmony_pad',a,2.5,root+interval,vel)
                        if tension>.78 and (name!='bassoon' or wood!='bassoon'):
                            for extra in ([0,3,12] if name=='horn' else [7]):
                                add(name,'harmony_pad',a,2.5,root+extra,vel-6)
            if tension>.78:
                for name,interval in [('trumpet',12),('trombone',0),('tuba',-24)]:
                    add(name,'harmony_pad',a,2,root+interval,vel)
                    if name!='tuba':add(name,'harmony_pad',a,2,root+interval+7,vel-4)
                add('timpani','bass',a,1,root-24,vel)
            if tension>.92 and bar%4==0:
                add('cymbals','percussion_layer',a,1,REGISTRY['cymbals']['comfortable'][0],vel)
        sections.append({**sec,'start_quarters':start,'end_quarters':end,
                         'start_seconds':start*60/bpm,'duration_seconds':length*60/bpm,
                         'proportion':length/(bars*4),'melody_instrument':target})
        start=end
    lines=[Line(f'{name}:{role}',role,tuple(events),
                (min(e.pitches[0] for e in events),max(e.pitches[0] for e in events)),
                .5,None,name) for (name,role),events in buckets.items()]
    score,assignment=orchestrate(lines,op)
    # Keep dynamics at changes and technique names at first use. Velocities in
    # the assignment remain untouched; this only removes redundant notation.
    for part in score.parts:
        last={}
        for item in list(part.recurse()):
            if isinstance(item,dynamics.Dynamic):kind='dynamic';value=item.value
            elif isinstance(item,expressions.TextExpression):kind='technique';value=item.content
            else:continue
            if last.get(kind)==value:item.activeSite.remove(item)
            else:last[kind]=value
    for sec in sections:
        score.parts[0].measure(int(sec['start_quarters']/4)+1).insert(0,expressions.TextExpression(sec['role']))
        active={}
        velocities=[]
        for player in assignment['players']:
            es=[e for e in player['events'] if sec['start_quarters']<=e['at']<sec['end_quarters']]
            if es:
                active[player['id']]={'attacks':len(es),'sounding_quarters':sum(e['duration'] for e in es)}
                velocities.extend(e['velocity'] for e in es)
        sec['usage']=active;sec['mean_velocity']=sum(velocities)/len(velocities)
        sec['peak_velocity']=max(velocities)
    return score,op,assignment,{'sections':sections,'returns':returns,'sources':sources,
                              'seconds':op['duration'],'bars':bars,'tempo':bpm}


def test_plan():
    source=school_material('tintinnabuli',62,19)
    # The upper M voice's first six attacks, retained with the source study.
    # Choose a connected contour from the reservoir rather than vertical chords.
    pitches=[62,64,65,69,67,64]
    theme={'pitches':pitches,'durations':[1,1,2,2,1,1],
           'source':{'kind':'rule-derived','school':'tintinnabuli','reservoir':source,
                     'editing':'six-note diatonic cell designed for this authorized test plan'}}
    def sections(form,bars,ops,shifts,curves):
        return [dict(role=r,bars=b,theme='distance',transform=o,shift=s,tension=t)
                for r,b,o,s,t in zip(FORMS[form],bars,ops,shifts,curves,strict=True)]
    return {'version':1,'title':'Memory of distance','seed':19,
      'concept':'A near contour becomes distant, breaks apart, and returns with space around it.',
      'method':'Cyclic interval contour; sonata conflict, slow arch, developing variations. No literal cluster events.',
      'themes':{'distance':theme},'orchestra':ORCHESTRA,
      'movements':[
       {'title':'Approach','tempo':64,'character':'restrained, then urgent','centre':62,
        'schools':['tintinnabuli'],'form':'sonata','sections':sections('sonata',[16,8,16,24,8,16,8],
        ['identity','fragmentation','augmentation','inversion','fragmentation','reharmonisation','augmentation'],
        [0,2,7,3,7,0,0],[[.2,.45],[.45,.6],[.3,.5],[.5,.95],[.85,.55],[.55,.8],[.7,.25]])},
       {'title':'Distance','tempo':64,'character':'suspended, inward','centre':65,
        'schools':['tintinnabuli','feldman'],'form':'arch','sections':sections('arch',[24,20,24,20,24],
        ['augmentation','inversion','fragmentation','reharmonisation','augmentation'],
        [0,-2,6,-2,0],[[.15,.3],[.3,.6],[.6,.82],[.55,.3],[.3,.12]])},
       {'title':'Return with space','tempo':80,'character':'gathering, then released','centre':62,
        'schools':['tintinnabuli','additive'],'form':'variations','sections':sections('variations',[24,28,32,32,24],
        ['identity','inversion','fragmentation','reharmonisation','augmentation'],
        [0,5,3,7,0],[[.25,.45],[.4,.7],[.6,.85],[.75,1],[.8,.08]])}]}


def join_scores(scores,title):
    joined=stream.Score();joined.atSoundingPitch=True;joined.metadata=metadata.Metadata(title=title)
    for pi in range(len(scores[0].parts)):
        part=stream.Part(id=scores[0].parts[pi].id);part.partName=scores[0].parts[pi].partName
        part.insert(0,deepcopy(scores[0].parts[pi].recurse().getElementsByClass('Instrument').first()))
        offset=0;number=1
        for score in scores:
            for measure in score.parts[pi].getElementsByClass('Measure'):
                copied=deepcopy(measure);copied.number=number;number+=1
                for ins in list(copied.recurse().getElementsByClass('Instrument')):ins.activeSite.remove(ins)
                part.insert(offset+measure.offset,copied)
            offset+=float(score.highestTime)
        joined.insert(0,part)
    return joined


def write_score(score,path):
    """Full-score XML with explicit MIDI ports; sounding notes stay unchanged."""
    import xml.etree.ElementTree as ET
    from .orchestra_render import strip_creator
    export=deepcopy(score)
    for i,part in enumerate(export.parts):
        for ins in part.recurse().getElementsByClass('Instrument'):
            if ins.midiChannel!=9:
                channel=i%15;ins.midiChannel=channel if channel<9 else channel+1
    export.write('musicxml',fp=path);strip_creator(path)
    tree=ET.parse(path)
    for i,part in enumerate(tree.findall('./part-list/score-part')):
        for midi in part.findall('midi-instrument'):
            channel=i%15
            if midi.findtext('midi-channel')!='10':
                midi.find('midi-channel').text=str(channel+(1 if channel<9 else 2))
            part.insert(list(part).index(midi),ET.Element('midi-device',{'id':midi.attrib['id'],'port':str(i//15+1)}))
    tree.write(path,encoding='utf-8',xml_declaration=True)


def produce(plan,out,bank,*,data=None,recipient=None):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from mnemosyne.weave import orchestral
    from .orchestra_render import render_orchestra, strip_creator
    validate(plan)
    if data is not None and recipient is None:raise ValueError('custom backup requires recipient public key')
    out=Path(out)
    if out.exists() and any(out.iterdir()):raise FileExistsError(f'preserved existing work: {out}')
    out.mkdir(parents=True,exist_ok=True)
    (out/'plan.json').write_text(json.dumps(plan,indent=2))
    built=[]
    for i in range(len(plan['movements'])):
        print(f'Composing movement {i+1}',flush=True);built.append(movement(plan,i))
    scores=[b[0] for b in built]
    # Public synthetic fixture only. Production callers MUST provide a recipient
    # public key; no recipient private key is read, logged or archived here.
    fixture=X25519PrivateKey.from_private_bytes(hashlib.sha256(b'symphony-public-test-fixture-v1').digest())
    data=data if data is not None else b'{"kind":"Namespace","metadata":{"name":"synthetic-symphony-test"},"apiVersion":"v1"}'
    report=orchestral.encode(scores,data,recipient or fixture.public_key())
    report['public_test_fixture']=recipient is None
    if recipient is None:
        if orchestral.decode(scores,fixture)!=data:raise ValueError('surface round trip failed')
    (out/'weave.json').write_text(json.dumps(report,indent=2))
    analyses=[]
    for i,(score,op,assignment,analysis) in enumerate(built,1):
        # Synchronize renderer's actual harp events with the woven score.
        for part,player in zip(score.parts,assignment['players'],strict=True):
            if player['instrument']=='harp':
                pitches={float(n.offset):n.pitch.ps for n in part.flatten().notes}
                for event in player['events']:event['pitches']=(pitches[event['at']],)
        op['symphony_plan']=plan;op['movement_index']=i
        (out/f'mv{i}-development.json').write_text(json.dumps(analysis,indent=2))
        dest=out/f'mv{i}';render_orchestra(score,op,assignment,dest,bank)
        analysis['render']=json.loads((dest/'analysis.json').read_text());analyses.append(analysis)
        (out/f'mv{i}-development.json').write_text(json.dumps(analysis,indent=2))
    return finalize(out)


def finalize(out):
    """Verify finished movement renders and publish the whole work, resumably.

    Never recompute encrypted surface notes or audio on recovery. A complete
    work is immutable; an incomplete finalization keeps its attempt directory.
    """
    import tempfile
    import shutil
    import numpy as np
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from mnemosyne.weave import orchestral
    from .orchestra_render import strip_creator
    out=Path(out)
    if (out/'work.json').exists():raise FileExistsError('already published symphony')
    plan=json.loads((out/'plan.json').read_text());validate(plan)
    count=len(plan['movements']);analyses=[]
    for i in range(1,count+1):
        destination=out/f'mv{i}'
        manifest=json.loads((destination/'render.json').read_text())
        for name,digest in manifest['artifacts'].items():
            if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=digest:raise ValueError(destination/name)
        rendered_plan=json.loads((destination/'plan.json').read_text())
        if rendered_plan['symphony_plan']!=plan:raise ValueError('mixed movement plans')
        analysis=json.loads((out/f'mv{i}-development.json').read_text())
        analysis['render']=json.loads((destination/'analysis.json').read_text())
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(destination/'score.mp3'),
            '-ar','8000','-ac','1','-f','f32le','-'])
        audio=np.frombuffer(raw,dtype='<f4')
        for section in analysis['sections']:
            start=round(section['start_seconds']*8000)
            end=round((section['start_seconds']+section['duration_seconds'])*8000)
            block=audio[start:end]
            rms=float(np.sqrt(np.mean(block**2)))
            section['audio_rms_dbfs']=20*math.log10(max(rms,1e-12))
            section['audio_peak']=float(np.max(np.abs(block)))
        analyses.append(analysis)
    scores=[converter.parse(out/f'mv{i}/score.musicxml').toSoundingPitch() for i in range(1,count+1)]
    report=json.loads((out/'weave.json').read_text())
    fixture=X25519PrivateKey.from_private_bytes(hashlib.sha256(b'symphony-public-test-fixture-v1').digest())
    if report.get('context_sha256') and hashlib.sha256(orchestral.context(scores)).hexdigest()!=report['context_sha256']:
        raise ValueError('published context changed')
    if report.get('envelope_sha256') and hashlib.sha256(orchestral.envelope(scores)).hexdigest()!=report['envelope_sha256']:
        raise ValueError('published envelope changed')
    if report['public_test_fixture']:
        restored=orchestral.decode(scores,fixture)
        report['published_musicxml_round_trip']=hashlib.sha256(restored).hexdigest()==report['payload_sha256']
        if not report['published_musicxml_round_trip']:raise ValueError('published payload changed')
    (out/'.drafts').mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='finalize-',dir=out/'.drafts'))
    combined=join_scores(scores,plan['title'])
    write_score(combined,work/'score.musicxml')
    recovered=converter.parse(work/'score.musicxml').toSoundingPitch()
    if orchestral.context([recovered])!=orchestral.context(scores):raise ValueError('combined score context changed')
    if orchestral.envelope([recovered])!=orchestral.envelope(scores):raise ValueError('combined envelope changed')
    if report['public_test_fixture']:
        report['combined_musicxml_round_trip']=orchestral.decode([recovered],fixture)==restored
        if not report['combined_musicxml_round_trip']:raise ValueError('combined payload changed')
    subprocess.run(['pdfunite',*[str(out/f'mv{i}/score.pdf') for i in range(1,count+1)],str(work/'score.pdf')],check=True)
    (work/'parts').mkdir()
    for part in sorted((out/'mv1/parts').glob('*.pdf')):
        subprocess.run(['pdfunite',*[str(out/f'mv{i}/parts'/part.name) for i in range(1,count+1)],str(work/'parts'/part.name)],check=True)
    inputs=[]
    for i in range(1,count+1):inputs.extend(['-i',str(out/f'mv{i}/score.mp3')])
    subprocess.run(['ffmpeg','-v','error',*inputs,'-filter_complex',f'concat=n={count}:v=0:a=1',
                    '-codec:a','libmp3lame','-q:a','2',str(work/'score.mp3')],check=True)
    measured=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration',
        '-of','json',str(work/'score.mp3')]))
    report['audio_seconds']=float(measured['format']['duration'])
    if abs(report['audio_seconds']-validate(plan)-sum(a['render']['tail_seconds'] for a in analyses))>.2:raise ValueError('combined audio duration changed')
    (work/'weave.json').write_text(json.dumps(report,indent=2))
    clock=0;curve=[]
    for analysis in analyses:
        for section in analysis['sections']:
            curve.append({'seconds':clock+section['start_seconds'],'target':section['tension'][0],
                'mean_velocity':section['mean_velocity'],'rms_dbfs':section['audio_rms_dbfs']})
        clock+=analysis['seconds']
    result={'seconds':validate(plan),'movements':analyses,'weave':report,'global_dynamic_curve':curve}
    (work/'analysis.json').write_text(json.dumps(result,indent=2))
    notes=[f"# {plan['title']}",'',
      f"Партитура: {validate(plan)/60:.2f} минут. Аудио: {report['audio_seconds']:.2f} с, включая хвосты зала.",
      f"Weave: {report['capacity_bytes']} байт ёмкости; {report['envelope_bytes']} байт конверта; {report['payload_bytes']} байт исходных данных.",
      'Синтетический Namespace — полный тестовый объект, не резервная копия целого кластера.',
      '', '| Часть | Длительность | Такты | Полные возвраты ячейки |', '|---|---:|---:|---:|']
    for i,analysis in enumerate(analyses,1):
        returns=sum(r['development']=='complete return' for r in analysis['returns'])
        notes.append(f"| {i}. {plan['movements'][i-1]['title']} | {analysis['seconds']:.0f} с | {analysis['bars']} | {returns} |")
    notes += ['', '## Форма, возвращения, оркестровка и динамика',
      'Циклические ячейки (MIDI / четверти): '+json.dumps({k:[v['pitches'],v['durations']] for k,v in plan['themes'].items()}),
      'В таблицах время дано от начала части. RMS измерен по готовому аудио; velocity — исполнительская интенсивность, не художественная оценка.']
    for i,analysis in enumerate(analyses,1):
        notes += ['',f"### Часть {i}",'', '| Раздел | Время, с | Тембр темы | Преобразование | Занятые партии | RMS, dBFS |',
                  '|---|---:|---|---|---:|---:|']
        for sec in analysis['sections']:
            notes.append(f"| {sec['role']} | {sec['start_seconds']:.1f} | {sec['melody_instrument']} | {sec['transform']} | {len(sec['usage'])} | {sec['audio_rms_dbfs']:.1f} |")
    notes += ['', '## Ограничения и слабые места',
      'Технический этюд движка, без слухового утверждения художественного качества. Секвенции регулярны, гармонический словарь узок, фигурация арфы почти постоянна.',
      'Школы дают исходные резервуары материала: это не воспроизведение всей фактуры или исторического стиля. Средние эпизоды местами разрежены.',
      'Оркестр использует секционные сэмплы и эвристический баланс. Между частями сохранены четырёхсекундные хвосты.',
      'Точные атаки возвратов, загрузка каждого инструмента и кривая всего цикла находятся в analysis.json. Звучащие длительности могут сокращаться на дыхание.',
      'Декодирование поддерживает общий MusicXML и упорядоченные MusicXML трёх частей; PDF и MP3 — представления произведения, не вход декодера.',
      'Публичный тестовый ключ не обеспечивает конфиденциальность. Для реальных данных требуется внешний ключ получателя.']
    (work/'REPORT.md').write_text('\n'.join(notes)+'\n')
    (work/'symphony-source.py').write_text(Path(__file__).read_text())
    weave_root=Path(orchestral.__file__).parent
    (work/'weave-sources.json').write_text(json.dumps({p.name:p.read_text() for p in weave_root.glob('*.py')},indent=2))
    # The pre-render capacity report is retained separately before publication.
    if (out/'weave.json').exists():
        shutil.copy2(out/'weave.json',work/'weave-before-publication.json')
    for source in work.rglob('*'):
        if source.is_file():
            target=out/source.relative_to(work);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists() and target.name!='weave.json':raise FileExistsError(target)
            shutil.copy2(source,target)
    files=[p for p in out.rglob('*') if p.is_file() and '.drafts' not in p.parts]
    (out/'work.json').write_text(json.dumps({'artifacts':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2))
    return report,analyses


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path);parser.add_argument('--write-test-plan',type=Path)
    parser.add_argument('--finish',type=Path,help='Finalize already rendered movements without recomposing');parser.add_argument('--out',type=Path);parser.add_argument('--sample-bank',type=Path,default=Path('/work/samples/instrumentarium'))
    parser.add_argument('--payload',type=Path);parser.add_argument('--recipient-public-key',type=Path)
    args=parser.parse_args()
    if args.write_test_plan:
        if args.write_test_plan.exists():raise FileExistsError(args.write_test_plan)
        args.write_test_plan.write_text(json.dumps(test_plan(),indent=2));return
    if args.finish:
        report,_=finalize(args.finish);print(json.dumps(report),flush=True);return
    if not args.plan or not args.out:parser.error('--plan and --out required')
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    recipient=X25519PublicKey.from_public_bytes(args.recipient_public_key.read_bytes()) if args.recipient_public_key else None
    plan=json.loads(args.plan.read_text())
    report,analyses=produce(plan,args.out,args.sample_bank,
        data=args.payload.read_bytes() if args.payload else None,recipient=recipient)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
