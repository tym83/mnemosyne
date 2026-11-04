"""Fetch preserved real works from studio-0 in verified resumable chunks.

Raw renderer intermediates stay in the pod. All composed/woven MusicXML,
plans, PDF/MP3, render provenance, source state and restore evidence are copied.
Existing local files are compared, never overwritten with different contents.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

KUBE=['kubectl','--kubeconfig',str(Path.home()/'workshop.txt'),'--context','admin@workshop',
      '-n','tenant-scheherazade','exec','studio-0','--','/work/venv/bin/python']
SNAPSHOT=r'''
import hashlib,json,os,sys,tarfile
from pathlib import Path
root=Path(sys.argv[1]);target=Path(sys.argv[2]);target.parent.mkdir(exist_ok=True)
files=[p for p in sorted(root.rglob('*')) if p.is_file() and '.drafts' not in p.parts]
records={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
with tarfile.open(target,'x:gz') as tar:
 for p in files:tar.add(p,arcname=str(p.relative_to(root)),recursive=False)
os.chmod(target,0o600)
chunks=[];whole=hashlib.sha256()
with target.open('rb') as f:
 while b:=f.read(1024*1024):
  whole.update(b);chunks.append({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()})
print(json.dumps({'archive':str(target),'sha256':whole.hexdigest(),'chunks':chunks,'files':records}))
'''
READ="import sys;f=open(sys.argv[1],'rb');f.seek(int(sys.argv[2]));sys.stdout.buffer.write(f.read(int(sys.argv[3])))"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not re.fullmatch(r'backup-e2e-[0-9]+',a.run):raise ValueError('invalid run')
    a.out.mkdir(parents=True,exist_ok=True);a.out.chmod(0o700)
    staging=a.out/'transfer';staging.mkdir(exist_ok=True,mode=0o700)
    record=staging/'transfer.json'
    remote=f'/work/{a.run}/works-export.tar.gz'
    if record.exists():manifest=json.loads(record.read_text())
    else:
        manifest=json.loads(subprocess.check_output(KUBE+['-c',SNAPSHOT,f'/work/{a.run}/result',remote]))
        record.write_text(json.dumps(manifest,indent=2));record.chmod(0o600)
    if manifest['archive']!=remote:raise ValueError('mismatched transfer')
    offset=0;whole=hashlib.sha256();archive=staging/'works.tar.gz'
    with archive.open('wb') as out:
        archive.chmod(0o600)
        for i,chunk in enumerate(manifest['chunks']):
            path=staging/f'{i:05d}.chunk'
            for attempt in range(3):
                if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==chunk['sha256']:break
                data=subprocess.check_output(KUBE+['-c',READ,remote,str(offset),str(chunk['bytes'])],timeout=45)
                if len(data)!=chunk['bytes'] or hashlib.sha256(data).hexdigest()!=chunk['sha256']:
                    if attempt==2:raise ValueError(f'chunk {i} mismatch')
                    continue
                path.write_bytes(data);path.chmod(0o600)
            data=path.read_bytes()
            if len(data)!=chunk['bytes'] or hashlib.sha256(data).hexdigest()!=chunk['sha256']:raise ValueError('bad retained chunk')
            out.write(data);whole.update(data);offset+=len(data)
            print(f'chunk {i+1}/{len(manifest["chunks"])} verified',flush=True)
    if whole.hexdigest()!=manifest['sha256']:raise ValueError('archive mismatch')
    with tarfile.open(archive) as tar:
        for member in tar:
            name=member.name
            if name not in manifest['files'] or not member.isfile():raise ValueError('unexpected archive entry')
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe archive path')
            data=tar.extractfile(member).read()
            if hashlib.sha256(data).hexdigest()!=manifest['files'][name]:raise ValueError(name)
            dest=a.out/relative
            if dest.exists():
                if dest.read_bytes()!=data:raise FileExistsError(f'different existing file: {dest}')
            else:
                dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open('xb') as f:f.write(data)
                dest.chmod(member.mode & 0o777)
    for name,digest in manifest['files'].items():
        if hashlib.sha256((a.out/name).read_bytes()).hexdigest()!=digest:raise ValueError(name)
    print(json.dumps({'verified_files':len(manifest['files']),'archive_bytes':offset,'sha256':whole.hexdigest()}))


if __name__=='__main__':main()
