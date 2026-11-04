"""Weave one school frame or recover a series from MusicXML and a private key."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from scheherazade.music.schools import SCHOOLS
from . import frames, fountain, payload, schools, surface


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key',type=Path,required=True)
    parser.add_argument('--mode',choices=('frames','fountain'),default='fountain')
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--payload',type=Path)
    parser.add_argument('--envelope',type=Path)
    parser.add_argument('--index',type=int,default=0)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--decode',nargs='+',type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if args.decode:
        key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
        roots = [surface.read(p) for p in args.decode]
        if args.mode=='fountain':
            data=fountain.recover([schools.read_fountain(r,key) for r in roots],key)
        else:
            data=frames.assemble([schools.read_frame(r,key) for r in roots],key)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('xb') as file:file.write(data)
        print(json.dumps({'recovered_bytes':len(data),'works':len(roots)}))
        return
    if args.plan is None or args.envelope is None:
        parser.error('encoding requires --plan and --envelope; use --payload to create a new envelope')
    plan=json.loads(args.plan.read_text())
    score=SCHOOLS[plan['school']].compose(plan,plan['seed'])
    with tempfile.TemporaryDirectory() as directory:
        xml=Path(directory)/'score.musicxml'
        score.write('musicxml',fp=xml)
        root=schools.prepare(surface.read(xml),plan['school'])
    cap=schools.capacity(root)
    overhead=frames.OVERHEAD if args.mode=='frames' else fountain.OVERHEAD+12
    if cap <= overhead:
        raise ValueError(f'plan provides {cap} bytes, but {args.mode} needs at least {overhead+1}')
    if not args.key.exists():
        if args.envelope.exists():raise ValueError('existing envelope requires its existing key')
        args.key.parent.mkdir(parents=True,exist_ok=True)
        with os.fdopen(os.open(args.key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as file:
            file.write(X25519PrivateKey.generate().private_bytes_raw())
    key=X25519PrivateKey.from_private_bytes(args.key.read_bytes())
    domain=frames.DOMAIN if args.mode=='frames' else fountain.DOMAIN
    if not args.envelope.exists():
        if args.payload is None:parser.error('a new envelope requires --payload')
        envelope=payload.seal(args.payload.read_bytes(),key.public_key(),context=domain)
        args.envelope.parent.mkdir(parents=True,exist_ok=True)
        with args.envelope.open('xb') as file:file.write(envelope)
    envelope=args.envelope.read_bytes()
    content=payload.open_envelope(envelope,key,context=domain)
    if args.payload is not None and content != args.payload.read_bytes():
        raise ValueError('saved envelope differs from supplied payload')
    if args.mode=='fountain':
        encoder=fountain.Encoder(envelope,cap-12,key)
        encoded=schools.weave_fountain(root,encoder,args.index,key)
        expected=encoder.frame(args.index)
        verify=lambda r: schools.read_fountain(r,key)==expected
        count=fountain.recommended_count(len(envelope),cap-12)
    else:
        encoded=schools.weave_frame(root,envelope,args.index,key)
        verify=lambda r: schools.read_frame(r,key)['index']==args.index
        count=(len(envelope)+cap-frames.OVERHEAD-1)//(cap-frames.OVERHEAD)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive creation preserves earlier works even in a concurrent invocation.
    with args.out.open('xb') as file:
        import xml.etree.ElementTree as ET
        ET.indent(encoded)
        ET.ElementTree(encoded).write(file,encoding='utf-8',xml_declaration=True)
    if not verify(surface.read(args.out)):
        raise RuntimeError('written MusicXML failed round trip')
    print(json.dumps({'capacity_bytes':cap,'index':args.index,'mode':args.mode,
                      'series_count_or_recommendation':count,'verified':True}))


if __name__=='__main__':main()
