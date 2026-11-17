"""Build a pinned VSCO CE subset as SF2 inside the studio (ffmpeg required).

Preserves SFZ key/velocity zones and sample tuning. Round robin is fixed to
its first take. Stereo is downmixed to mono; native sample tails are retained.
Sustained presets use documented crossfaded segments of their own samples. This is not a general SFZ converter.
"""
import argparse
import math
from .instrumentarium import REGISTRY, release_profile
from .sample_sustain import crossfade_loop, embedded_loop, audio_info
import numpy as np
import hashlib
import json
from pathlib import Path
import re
import struct as st
import subprocess
from urllib.parse import quote
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
import time

REVISION = '6dd651d55dde97fd4028699be9d4481f26917891'
BASE = f'https://raw.githubusercontent.com/sgossner/VSCO-2-CE/{REVISION}/'
PRESETS = {0:'UprightPiano',40:'SViolinVib',41:'ViolaEnsSusVib',42:'CelloEnsSusVib',
           43:'ContrabassSusVB',71:'ClarinetSus',73:'FluteSusNV',48:'ViolinEnsSusVib'}


def chunk(tag, data):
    return tag.encode()+st.pack('<I',len(data))+data+(b'\0' if len(data)%2 else b'')


def label(s):
    return s.encode()[:19].ljust(20,b'\0')


def opened(url, attempts=6):
    """A download that waits out a sample host's passing outage (5xx, 429, dropped connection)."""
    for attempt in range(attempts):
        try:
            return urlopen(url, timeout=120)
        except HTTPError as exc:
            if exc.code < 500 and exc.code != 429 or attempt + 1 == attempts:
                raise
        except URLError:
            if attempt + 1 == attempts:
                raise
        time.sleep(5 * 2 ** attempt)


def fetch(path, root):
    dest = root/path
    if not dest.exists():
        dest.parent.mkdir(parents=True,exist_ok=True)
        with opened(BASE+quote(path,safe='/')) as response:
            data = response.read()
        dest.write_bytes(data)
    return dest


def build(root, output_root=None):
    root.mkdir(parents=True,exist_ok=True)
    fetch('LICENSE',root)
    fetch('Readme.txt',root)
    samples = bytearray()
    shdr,phdr,pbag,pgen,inst,ibag,igen = [bytearray() for _ in range(7)]
    provenance = []
    def gen(op,value):
        return st.pack('<HH',op,value & 65535)
    for index,(program,name) in enumerate(PRESETS.items()):
        sfz = fetch(name+'.sfz',root).read_text()
        default = re.search(r'default_path=(.*)',sfz).group(1).strip().replace('\\','/')
        phdr.extend(st.pack('<20sHHHIII',label(name),program,0,index,0,0,0))
        pbag.extend(st.pack('<HH',index,0))
        pgen.extend(gen(41,index))
        inst.extend(st.pack('<20sH',label(name),len(ibag)//4))
        regions = []
        for region in sfz.split('<region>')[1:]:
            region = region.split('<group>')[0]
            values = dict(re.findall(r'(\w+)\s*=\s*([^\r\n]+)',region))
            if int(values.get('seq_position','1')) != 1:
                continue
            regions.append(values)
        bounds = {0:(21,108),40:(55,103),41:(48,88),42:(36,84),43:(28,67),71:(50,94),73:(60,96),48:(55,103)}
        original_regions = [v.copy() for v in regions]
        for values in regions:
            peers = [v for v in original_regions if (v.get('lovel','0'),v.get('hivel','127')) == (values.get('lovel','0'),values.get('hivel','127'))]
            original_zone = [int(values['lokey']),int(values['hikey'])]
            if original_zone[0] == min(int(v['lokey']) for v in peers):
                values['lokey'] = str(min(original_zone[0],bounds[program][0]))
            if original_zone[1] == max(int(v['hikey']) for v in peers):
                values['hikey'] = str(max(original_zone[1],bounds[program][1]))
            relative = default+values['sample'].strip().replace('\\','/')
            source = fetch(relative,root)
            raw = subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(source),
                '-ac','1','-ar','44100','-f','s16le','-'])
            pcm = np.frombuffer(raw,dtype='<i2').astype(np.float64)
            requested_gain = 10**(float(values.get('volume','0'))/20)
            gain = min(requested_gain,32700/max(1,float(np.max(np.abs(pcm)))))
            instrument_name = next(n for n,spec in REGISTRY.items() if spec.get('gm_program') == program and not spec.get('unpitched'))
            profile = release_profile(instrument_name)
            loop = None
            loop_kind = 'natural-decay'
            pcm = pcm * gain
            if profile.get('sustained'):
                native = embedded_loop(source)
                if native:
                    rate = audio_info(str(source))['rate']
                    loop = tuple(round(x*44100/rate) for x in native)
                    loop_kind = 'library-loop'
                else:
                    pcm, begin, end = crossfade_loop(pcm, 44100)
                    loop = begin, end
                    loop_kind = 'same-sample-crossfade'
            raw = np.rint(pcm).astype('<i2').tobytes()
            start = len(samples)//2
            size = len(raw)//2
            samples.extend(raw+b'\0'*92)
            sid = len(shdr)//46
            key = int(values['pitch_keycenter'])
            shdr.extend(st.pack('<20sIIIIIBbHH',label(f'{name[:10]}{sid}'),start,start+size,
                start+(loop[0] if loop else 0),start+(loop[1]+1 if loop else size-1),44100,key,0,0,1))
            ibag.extend(st.pack('<HH',len(igen)//4,0))
            igen.extend(gen(43,int(values['lokey']) | int(values['hikey'])<<8))
            igen.extend(gen(44,int(values.get('lovel',0)) | int(values.get('hivel',127))<<8))
            igen.extend(gen(34,-12000))  # ~1 ms attack
            igen.extend(gen(38,round(1200*math.log2(profile['release_seconds']))))
            if loop: igen.extend(gen(54,1))  # continuous loop through the release envelope
            igen.extend(gen(53,sid))
            provenance.append({'path':relative,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'program':program,'key':key,'low':int(values['lokey']),'high':int(values['hikey']),
                'lovel':int(values.get('lovel',0)),'hivel':int(values.get('hivel',127)),
                'release_seconds':profile['release_seconds'],'sustain':loop_kind,'loop':loop,
                'requested_gain':requested_gain,'applied_gain':gain,'original_zone':original_zone,'sample_seconds':size/44100})
        print('converted',name,flush=True)
    phdr.extend(st.pack('<20sHHHIII',label('EOP'),0,0,len(pbag)//4,0,0,0))
    pbag.extend(st.pack('<HH',len(pgen)//4,0)); pgen.extend(b'\0'*4)
    inst.extend(st.pack('<20sH',label('EOI'),len(ibag)//4))
    ibag.extend(st.pack('<HH',len(igen)//4,0)); igen.extend(b'\0'*4)
    shdr.extend(st.pack('<20sIIIIIBbHH',label('EOS'),*[0]*9))
    def text_chunk(tag, text):
        data = text.encode()+b'\0'
        if len(data)%2:
            data += b'\0'
        return chunk(tag,data)
    info = chunk('LIST',b'INFO'+chunk('ifil',st.pack('<HH',2,1))+chunk('isng',b'EMU8000\0')+
        chunk('INAM',b'VSCO CE school subset\0')+text_chunk('ICOP','CC0; Versilian Studios, Sam Gossner, Simon Dalzell'))
    pdta = chunk('LIST',b'pdta'+b''.join(chunk(k,v) for k,v in [
        ('phdr',phdr),('pbag',pbag),('pmod',b'\0'*10),('pgen',pgen),('inst',inst),
        ('ibag',ibag),('imod',b'\0'*10),('igen',igen),('shdr',shdr)]))
    output_root = Path(output_root or root)
    output_root.mkdir(parents=True,exist_ok=True)
    if output_root != root:
        import shutil
        shutil.copy2(root/'LICENSE', output_root/'LICENSE')
    output = output_root/'vsco-schools.sf2'
    output.write_bytes(chunk('RIFF',b'sfbk'+info+chunk('LIST',b'sdta'+chunk('smpl',samples))+pdta))
    (output_root/'manifest.json').write_text(json.dumps({'revision':REVISION,'conversion_version':4,
        'sf2_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'samples':provenance},indent=2))
    print(output,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,help='New SF2 bank directory; retain the source sample cache')
    parser.add_argument('--native', action='store_true', help='Preserve stereo SFZ, layers and round robins')
    args = parser.parse_args()
    if args.native:
        from .native_bank import prepare
        prepare(args.directory)
    else:
        build(args.directory,args.output)
