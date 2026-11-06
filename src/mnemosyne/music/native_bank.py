"""Pinned native SFZ banks, provenance and fail-closed key/velocity coverage.

Playback belongs to sfizz; the parser below only resolves includes, macros and
region inheritance for coverage/provenance. It does not synthesize SFZ opcodes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
from urllib.request import urlopen
import shutil
import yaml
from .instrumentarium import ROOT, REGISTRY, sample_patch

LIBRARIES=yaml.safe_load((ROOT/'sample_libraries.yaml').read_text())['libraries']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def download(url,path):
    path=Path(path)
    if path.exists():return
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.partial')
    with urlopen(url,timeout=120) as src, temp.open('wb') as out:
        shutil.copyfileobj(src,out)
    temp.replace(path)


def install_library(root,name):
    info=LIBRARIES[name];target=root/name
    stamp=target/'revision.json'
    if stamp.exists():
        if json.loads(stamp.read_text())['revision']!=info['revision']:
            raise ValueError(f'Existing library revision mismatch: {target}')
        return
    archive=root/(name+'.tar.gz')
    download(f'https://codeload.github.com/{info["repository"]}/tar.gz/{info["revision"]}',archive)
    # A prior interrupted extraction can be resumed from the identical archive.
    target.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar:
            relative=Path(member.name).parts[1:]
            if not relative:continue
            member.name=str(Path(*relative))
            if member.issym() or member.islnk():raise ValueError('Unexpected archive link')
            tar.extract(member,target,filter='data')
    stamp.write_text(json.dumps({'revision':info['revision'],'archive_sha256':sha(archive)}))


def preprocess(path,macros=None,stack=()):
    """SFZ directives are interpreted in textual order, preserving group state."""
    path=Path(path).resolve();macros={} if macros is None else macros
    if path in stack:raise ValueError(f'Cyclic SFZ include: {path}')
    result=[]
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.split('//',1)[0].strip()
        if line.startswith('#define'):
            _,key,value=line.split(maxsplit=2);macros[key]=value;continue
        for key,value in sorted(macros.items(),key=lambda x:-len(x[0])):
            line=line.replace(key,value)
        match=re.fullmatch(r'#include\s+"([^"]+)"',line)
        if match:
            result.append(preprocess(path.parent/match[1].replace('\\','/'),macros,(*stack,path)))
        elif line.startswith('#'):
            raise ValueError(f'Unsupported SFZ directive: {line}')
        else:result.append(line)
    return '\n'.join(result)


def keynum(value):
    try:return int(value)
    except ValueError:
        match=re.fullmatch(r'([a-gA-G])([#b]?)(-?\d+)',value)
        if not match:raise ValueError(f'Invalid SFZ key {value!r}')
        note,acc,octave=match.groups()
        return (int(octave)+1)*12+{'c':0,'d':2,'e':4,'f':5,'g':7,'a':9,'b':11}[note.lower()]+{'':0,'#':1,'b':-1}[acc]


def regions(path):
    source=preprocess(path)
    global_,master,group,control={},{},{},{}
    result=[]
    for kind,body in re.findall(r'<(\w+)>([^<]*)',source):
        values={k:v.strip() for k,v in re.findall(r'(\w+)\s*=\s*(.*?)(?=\s+\w+\s*=|$)',body,re.S)}
        if kind=='control':control.update(values)
        elif kind=='global':global_=values;master={};group={}
        elif kind=='master':master=values;group={}
        elif kind=='group':group=values
        elif kind=='region':
            zone={**global_,**master,**group,**values}
            if 'sample' not in zone:raise ValueError(f'Region without sample: {path}')
            sample=(path.parent/control.get('default_path','').replace('\\','/')/zone['sample'].replace('\\','/')).resolve()
            if not sample.is_file():
                if 'shinyguitar' in str(path):
                    sample=path.parent/'../Samples'/zone['sample'].replace('\\','/')
                sample=canonical_file(sample)
            key=zone.get('key')
            result.append({'low':keynum(zone.get('lokey',key or '0')),'high':keynum(zone.get('hikey',key or '127')),
                'lovel':int(zone.get('lovel',0)),'hivel':int(zone.get('hivel',127)),
                'trigger':zone.get('trigger','attack'),'sample':str(sample),
                'seq_length':int(zone.get('seq_length',1)),'seq_position':int(zone.get('seq_position',1)),
                'opcodes':zone})
    if not result:raise ValueError(f'No SFZ regions: {path}')
    return result


def audit_patch(root,instrument,technique):
    library,relative=sample_patch(instrument,technique)
    path=root/library/relative
    zones=regions(path)
    return {'instrument':instrument,'technique':technique,'library':library,'patch':relative,
            'sha256':sha(path),'regions':zones}


def check_coverage(patch,pitch,velocity):
    key=round(pitch)
    declared=REGISTRY.get(patch['instrument'],{}).get('samples',{}).get('key_ranges',{}).get(patch['technique'],[])
    if declared and not any(low<=key<=high for low,high in declared):
        raise ValueError(f'{patch["instrument"]}: key {key} is not a sounding-pitch mapping for {patch["technique"]}')
    if not any(z['low']<=key<=z['high'] and z['lovel']<=velocity<=z['hivel'] and z['trigger'] in ('attack','first','legato') for z in patch['regions']):
        raise ValueError(f'{patch["instrument"]}/{patch["technique"]} lacks sample at pitch={pitch}, velocity={velocity}')


def install_dan_tranh(root):
    from urllib.parse import quote
    info=LIBRARIES['vcsl'];base=f'https://raw.githubusercontent.com/{info["repository"]}/{info["revision"]}/'
    folder=root/'vcsl';folder.mkdir(exist_ok=True)
    for path in info['subset']+info['license_files']:
        download(base+quote(path,safe='/'),folder/path)
    by_dynamic={}
    for path in info['subset']:
        name,dynamic,rr=Path(path).stem.split('_')
        by_dynamic.setdefault(dynamic,[]).append((keynum(name)+12,path))
    lines=['// Native VCSL samples, filenames C3=middle C. No artificial loops.']
    for dynamic,(lo,hi) in {'mf':(0,63),'f':(64,95),'ff':(96,127)}.items():
        entries=sorted(by_dynamic[dynamic])
        for i,(key,path) in enumerate(entries):
            low=(entries[i-1][0]+key)//2+1 if i else 47
            high=(key+entries[i+1][0])//2 if i+1<len(entries) else 83
            lines.append(f'<region> sample={path}\nlokey={low} hikey={high} pitch_keycenter={key} lovel={lo} hivel={hi} ampeg_release=1')
    (folder/'dan_tranh.sfz').write_text('\n'.join(lines)+'\n')


def prepare(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    for name in ('sso','shinyguitar','button_accordion'):
        install_library(root,name)
    install_dan_tranh(root)
    ir=LIBRARIES['openair_jack_lyons']
    download(ir['download'],root/'hall.wav')
    download('https://webfiles.york.ac.uk/OPENAIR/IRs/jack-lyons-concert-hall-university-york/Read%20Me.txt',root/'hall-readme.txt')
    result=[];failures=[]
    for name,spec in REGISTRY.items():
        for technique in spec['samples']['patches']:
            try:
                info=audit_patch(root,name,technique)
                result.append({'instrument':name,'technique':technique,'regions':len(info['regions']),
                               'round_robins':max(z['seq_length'] for z in info['regions'])})
            except (ValueError,FileNotFoundError) as exc:failures.append(str(exc))
    (root/'coverage.json').write_text(json.dumps({'patches':result,'failures':failures},indent=2))
    print(json.dumps({'patches':len(result),'failures':failures}),flush=True)
    if failures:raise SystemExit(1)




def canonical_file(path):
    """Resolve legacy Windows SFZ filename case without altering source files."""
    path=Path(path).resolve()
    if path.exists():return path
    parent=canonical_file(path.parent)
    matches=[p for p in parent.iterdir() if p.name.casefold()==path.name.casefold()]
    if len(matches)!=1:raise FileNotFoundError(path)
    return matches[0]


def playback_patch(root,instrument,technique,destination):
    library,relative=sample_patch(instrument,technique)
    path=root/library/relative
    source=preprocess(path)
    default='../Samples/' if library=='shinyguitar' else ''
    match=re.search(r'\bdefault_path\s*=\s*([^\r\n]+)',source)
    if match:default=match[1].strip()
    source=re.sub(r'\bdefault_path\s*=\s*[^\r\n]+','',source)
    def replace_sample(match):
        sample=canonical_file(path.parent/default.replace('\\','/')/match[1].strip().replace('\\','/'))
        return 'sample='+str(sample)+'\n'
    source=re.sub(r'\bsample\s*=\s*(.*?)(?=\s+\w+\s*=|\r?\n|$)',replace_sample,source)
    # Some instruments select round robins randomly. Cycle those takes in a
    # stable order instead; retain all samples, unlike the legacy first-RR bank.
    def stable_round_robin(match):
        body=match[1]
        lo=re.search(r'\blorand=([\d.]+)',body);hi=re.search(r'\bhirand=([\d.]+)',body)
        if lo or hi:
            low=float(lo[1]) if lo else 0;high=float(hi[1]) if hi else 1
            if high<=low:raise ValueError('Invalid random SFZ region')
            length=round(1/(high-low));position=round(low*length)+1
            if abs(length*(high-low)-1)>.001:raise ValueError('Nonuniform random region needs explicit mapping')
            body=re.sub(r'\b(?:lo|hi)rand=[\d.]+','',body)
            body+=f'\nseq_length={length} seq_position={position}\n'
        return '<region>'+body
    source=re.sub(r'<region>([^<]*)',stable_round_robin,source)
    # Explicit common bend range makes quarter tones and glissandi independent
    # of a library's default two-semitone pitch wheel range.
    source=re.sub(r'(<region>)',r'\1 bend_up=1200 bend_down=-1200 ',source)
    destination.write_text(source)
    from .instrumentarium import release_profile
    from .sample_sustain import prepare_region
    profile = release_profile(instrument)
    # Pizzicato/staccato and other struck techniques must retain natural decay.
    profile = {**profile, 'sustained': profile.get('sustained') and technique in ('sustain','arco','tremolo')}
    zones = iter(regions(destination)); manifest = []
    def sustain_region(match):
        zone = next(zones)
        overrides, measured = prepare_region(zone, profile, destination)
        body = match[1]
        for key, value in overrides.items():
            body = re.sub(r'\b'+key+r'\s*=\s*.*?(?=\s+\w+\s*=|$)', '', body, flags=re.S)
            body += f'\n{key}={value}\n'
        manifest.append(measured)
        return '<region>'+body
    source = re.sub(r'<region>([^<]*)', sustain_region, source)
    destination.write_text(source)
    destination.with_suffix('.samples.json').write_text(json.dumps(manifest, indent=2))
    return destination


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path)
    prepare(ap.parse_args().root)
