"""Pod-only real school music backup. Keeps every source, draft and render.

No model calls. Plans are the existing orchestrated method studies. Commands
are separate so measured works can be inspected before loss/application.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

import yaml
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.state.collect import archive, normalize
from mnemosyne.restore import Kubectl, identity, read_archive
from mnemosyne.weave import fountain, payload, registry, schools, school_series, surface
from mnemosyne.weave.backup import write_new

FRAME_BYTES = 256
SCHOOL_CYCLE = ('tempo_canon', 'sonorism', 'drone')


def save(path, value):
    write_new(path, json.dumps(value, indent=2, ensure_ascii=False).encode())


def prepare(source, output, count):
    from mnemosyne.music.schools import SCHOOLS
    from mnemosyne.music.orchestration import orchestrate, school_lines
    from mnemosyne.music.render import note_events
    from music21 import converter
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = archive(yaml.safe_load_all(source.read_text()))
    write_new(output/'source.tar.zst', data)
    shutil.copy2(source, output/'source.yaml')
    key = X25519PrivateKey.generate()
    write_new(output/'recipient.key', key.private_bytes_raw())
    envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
    write_new(output/'envelope.bin', envelope)
    encoder = fountain.Encoder(envelope, FRAME_BYTES, key)
    full = output/'full'; full.mkdir()
    rows = []; index = 0
    plans = Path(__import__('mnemosyne').__file__).parent/'music/schools/orchestrated_plans'
    for number in range(count):
        name = SCHOOL_CYCLE[number % len(SCHOOL_CYCLE)]
        work_id = f'{number:03d}-{name}'
        dest = full/work_id; dest.mkdir()
        plan = json.loads((plans/f'{name}.json').read_text())
        save(dest/'source-plan.json', plan)
        plan['seed'] += number//len(SCHOOL_CYCLE)
        plan['backup_series'] = {'work':work_id, 'source_plan':str(plans/f'{name}.json')}
        save(dest/'plan.json', plan)
        score = SCHOOLS[name].compose(plan, plan['seed'])
        score.write('musicxml', fp=dest/'composition.musicxml')
        assignment = None
        if plan.get('audio_profile') != 'technique_synthesis':
            score, assignment = orchestrate(school_lines(score, plan), plan)
            save(dest/'orchestration.json', assignment)
        for i, part in enumerate(score.parts):
            ins = part.recurse().getElementsByClass('Instrument').first()
            if ins.midiChannel != 9:
                c = i % 15; ins.midiChannel = c if c<9 else c+1
        score.write('musicxml', fp=dest/'orchestrated.musicxml')
        root = schools.prepare(surface.read(dest/'orchestrated.musicxml'), name)
        root = registry.mark(root, (name, 'dynamics-fountain', '2'))
        cap = schools.capacity(root)
        slots = (cap-school_series.OVERHEAD)//FRAME_BYTES
        if slots < 5: raise ValueError(f'{work_id}: only {slots} frames')
        indices = list(range(index,index+slots)); index += slots
        woven = school_series.encode_many(root,[encoder.frame(i) for i in indices],key)
        surface.write(woven,dest/'work.musicxml')
        actual = registry.decode(dest/'work.musicxml',key).frame
        if actual != [encoder.frame(i) for i in indices]: raise RuntimeError('XML decode mismatch')
        parsed = converter.parse(dest/'work.musicxml').toSoundingPitch()
        if note_events(parsed.stripTies()) != note_events(score.stripTies()):
            raise RuntimeError('weaving changed sounding notes')
        row = {'id':work_id,'school':name,'ensemble':plan.get('orchestration',plan['ensemble']),
               'seconds':plan['duration'],'capacity':cap,'indices':indices,'notes_unchanged':True}
        save(dest/'backup.json',row); rows.append(row)
        print(json.dumps(row),flush=True)
    save(output/'series.json',{'archive_bytes':len(data),'archive_sha256':hashlib.sha256(data).hexdigest(),
         'envelope_bytes':len(envelope),'k':encoder.k,'frame_bytes':FRAME_BYTES,'works':rows,
         'snapshot':encoder.snapshot.hex()})


def render(output, only=None):
    from mnemosyne.music.schools import SCHOOLS
    from mnemosyne.music.orchestration import orchestrate, school_lines
    from mnemosyne.music.orchestra_render import render_orchestra
    from mnemosyne.music.render import render_score
    from mnemosyne.music.native_bank import sha
    info = (json.loads((output/'series.json').read_text()) if (output/'series.json').exists()
            else {'works':[json.loads(p.read_text()) for p in sorted((output/'full').glob('*/backup.json'))]})
    for row in info['works']:
        if only and row['id'] not in only: continue
        dest = output/'full'/row['id']; rendered = dest/'render'
        if (rendered/'render.json').exists():
            manifest=json.loads((rendered/'render.json').read_text())
            for name,digest in manifest['artifacts'].items():
                if sha(rendered/name)!=digest: raise ValueError('changed render artifact')
            continue
        plan=json.loads((dest/'plan.json').read_text())
        score=SCHOOLS[plan['school']].compose(plan,plan['seed'])
        if plan.get('audio_profile')!='technique_synthesis':
            score,assignment=orchestrate(school_lines(score,plan),plan)
        curves=schools.expression_curves(surface.read(dest/'work.musicxml'))
        for part,curve in zip(score.parts,curves,strict=True):part.editorial.school_expression=curve
        bank=Path('/work/samples/instrumentarium')
        if plan.get('audio_profile')=='technique_synthesis':render_score(score,plan,rendered,bank)
        else:render_orchestra(score,plan,assignment,rendered,bank)
        print('COMPLETE',row['id'],flush=True)


def rank(masks):
    rows={}
    for mask in masks:
        while mask:
            pivot=mask.bit_length()-1
            if pivot not in rows:rows[pivot]=mask;break
            mask ^= rows[pivot]
    return len(rows)


def notation(output):
    """Keep original PDFs; make a legible conductor export without repeated labels."""
    import xml.etree.ElementTree as ET
    from music21 import converter
    from mnemosyne.music.render import note_events, run
    for row in json.loads((output/'series.json').read_text())['works']:
        dest=output/'full'/row['id']; target=dest/'notation-v2'
        if (target/'verified.json').exists():continue
        if not (dest/'render/render.json').exists():continue
        target.mkdir(exist_ok=True)
        tree=ET.parse(dest/'render/score.musicxml')
        for part in tree.findall('part'):
            previous=None
            for measure in part.findall('measure'):
                for direction in list(measure.findall('direction')):
                    word=direction.find('direction-type/words')
                    if word is None or word.text not in ('sustain','arco','pizzicato','staccato'):continue
                    if word.text==previous and len(direction.findall('direction-type'))==1 and len(direction.find('direction-type'))==1 and direction.find('sound') is None:
                        measure.remove(direction)
                    else:previous=word.text
        xml=target/'score.musicxml';tree.write(xml,encoding='utf-8',xml_declaration=True)
        a,b=[converter.parse(p).toSoundingPitch().stripTies() for p in (dest/'render/score.musicxml',xml)]
        if note_events(a)!=note_events(b):raise RuntimeError('engraving changed notes')
        log=target/'render.log';run(['musicxml2ly','-o',target/'score.ly',xml],log)
        # Ten-plus staff conductor scores need room for the entire system.
        if len(a.parts)>=10:
            ly=target/'score.ly'
            text=ly.read_text().replace('#(set-global-staff-size 20.0)', '#(set-global-staff-size 14)')
            text=text.replace('\\paper {', '\\paper {\n    #(set-paper-size "a3")\n    systems-per-page = #1', 1)
            ly.write_text(text)
        run(['lilypond','-dno-point-and-click','-o',target/'score',target/'score.ly'],log)
        warnings=[line for line in log.read_text().splitlines() if 'warning:' in line.lower() or 'error:' in line.lower()]
        save(target/'verified.json',{'notes_unchanged':True,'warnings':warnings,
             'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}})
        print('NOTATION',row['id'],json.dumps(warnings),flush=True)


def loss(output):
    info=json.loads((output/'series.json').read_text()); works=info['works']
    key=X25519PrivateKey.from_private_bytes((output/'recipient.key').read_bytes())
    masks=[]
    for work in works:
        frames=registry.decode(output/'full'/work['id']/'work.musicxml',key).frame
        decoded=[fountain.unpack(frame,key) for frame in frames]
        if [f[1] for f in decoded]!=work['indices']:raise ValueError('frame indices differ')
        if any(f[0].hex()!=info['snapshot'] or f[2]!=info['k'] for f in decoded):
            raise ValueError('snapshot or dimensions differ')
        masks.append([fountain.coefficients(f[0],f[1],f[2]) for f in decoded])
    n=len(works); lost=math.ceil(n*.3); retain=n-lost
    combinations=math.comb(n,retain)
    if combinations>1000000:raise ValueError('too many exhaustive subsets; do not claim any-70%')
    start=time.monotonic();minimum=info['k']
    for chosen in itertools.combinations(range(n),retain):
        r=rank(m for j in chosen for m in masks[j]);minimum=min(minimum,r)
        if r<info['k']:raise ValueError(f'rank-deficient subset: {chosen}')
    save(output/'all-subsets.json',{'works':n,'lost':lost,'retained':retain,'subsets':combinations,
         'minimum_rank':minimum,'required_rank':info['k'],'seconds':time.monotonic()-start})
    seed=20261104
    missing=set(random.Random(seed).sample(range(n),lost))
    survivors=output/'surviving-musicxml';survivors.mkdir()
    for i,w in enumerate(works):
        if i not in missing:shutil.copy2(output/'full'/w['id']/'work.musicxml',survivors/(w['id']+'.musicxml'))
    save(output/'loss.json',{'seed':seed,'lost':[w['id'] for i,w in enumerate(works) if i in missing],
         'survived':[w['id'] for i,w in enumerate(works) if i not in missing],
         'method':'copy survivors only; original works and all drafts remain in full/'})


def differences(expected, actual, path=''):
    if isinstance(expected,list) and isinstance(actual,list):
        result=[]
        for i in range(max(len(expected),len(actual))):
            p=path+'/'+str(i)
            if i>=len(expected):result.append({'path':p,'change':'added','actual':actual[i]})
            elif i>=len(actual):result.append({'path':p,'change':'missing','expected':expected[i]})
            else:result.extend(differences(expected[i],actual[i],p))
        return result
    if isinstance(expected,dict) and isinstance(actual,dict):
        result=[]
        for key in sorted(expected.keys()|actual.keys()):
            p=path+'/'+key
            if key not in expected:result.append({'path':p,'change':'added','actual':actual[key]})
            elif key not in actual:result.append({'path':p,'change':'missing','expected':expected[key]})
            else:result.extend(differences(expected[key],actual[key],p))
        return result
    if expected!=actual:return [{'path':path,'change':'changed','expected':expected,'actual':actual}]
    return []


def apply(output,kubeconfig,context):
    start=time.monotonic()
    command=[sys.executable,'-m','mnemosyne.restore','--works',str(output/'surviving-musicxml'),
             '--key',str(output/'recipient.key'),'--apply','--output',str(output/'restored'),
             '--kubeconfig',str(kubeconfig),'--context',context]
    with (output/'restore.log').open('x') as log:subprocess.run(command,stdout=log,stderr=log,check=True)
    elapsed=time.monotonic()-start
    data=(output/'source.tar.zst').read_bytes()
    if (output/'restored/archive.tar.zst').read_bytes()!=data:raise RuntimeError('archive differs')
    api=Kubectl(kubeconfig,context); rows=[]
    for obj in read_archive(data):
        base,resource=api.resource(obj['apiVersion'],obj['kind'])
        if resource['namespaced']:base+='/namespaces/'+obj['metadata']['namespace']
        actual=normalize(api.run(['get','--raw',base+'/'+resource['name']+'/'+obj['metadata']['name']]))
        diff=differences(obj,actual)
        rows.append({'identity':identity(obj),'exact_normalized':not diff,'differences':diff})
    save(output/'comparison.json',{'restore_seconds':elapsed,'archive_identical':True,'objects':rows,
                                 'exact_normalized':sum(r['exact_normalized'] for r in rows)})
    print(json.dumps({'restore_seconds':elapsed,'objects':len(rows),'exact_normalized':sum(r['exact_normalized'] for r in rows)}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('prepare','render','notation','loss','apply'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--source',type=Path)
    p.add_argument('--count',type=int,default=19)
    p.add_argument('--only',nargs='+')
    p.add_argument('--kubeconfig',type=Path);p.add_argument('--context')
    a=p.parse_args()
    if a.command=='prepare':prepare(a.source,a.out,a.count)
    elif a.command=='render':render(a.out,a.only)
    elif a.command=='notation':notation(a.out)
    elif a.command=='loss':loss(a.out)
    else:
        if not a.kubeconfig or not a.context:p.error('apply requires explicit kubeconfig and context')
        apply(a.out,a.kubeconfig,a.context)


if __name__=='__main__':main()
