"""Snapshot completed studio works; transfer resumable, independently hashed chunks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time

KUBE=['kubectl','--kubeconfig',str(Path.home()/'workshop.txt'),'--context','admin@workshop','-n','tenant-scheherazade','exec','studio-0','--']

SNAPSHOT=r'''
import hashlib,json,sys,tarfile
from pathlib import Path
source=Path(sys.argv[1]);archive=Path(sys.argv[2]);archive.parent.mkdir(parents=True,exist_ok=True)
files=[]
for manifest in sorted(source.rglob('render.json')):
 if '.drafts' in manifest.parts:continue
 data=json.loads(manifest.read_text())
 for name,digest in data['artifacts'].items():
  p=manifest.parent/name
  if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError(str(p))
  files.append(p)
 files.append(manifest)
files.extend(source.glob('run-*.json'))
with tarfile.open(archive,'w:gz') as tar:
 for path in files:tar.add(path,arcname=str(path.relative_to(source)),recursive=False)
chunks=[];full=hashlib.sha256()
with archive.open('rb') as f:
 while data:=f.read(1024*1024):
  full.update(data);chunks.append({'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
print(json.dumps({'archive':str(archive),'size':archive.stat().st_size,'sha256':full.hexdigest(),'chunks':chunks}))
'''
READ="import sys; f=open(sys.argv[1],'rb'); f.seek(int(sys.argv[2])); sys.stdout.buffer.write(f.read(int(sys.argv[3])))"


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True)
    ap.add_argument('--resume',type=Path,help='Resume a retained chunks-* transfer directory')
    ap.add_argument('--out',type=Path,default=Path('out/works/music/ensembles'))
    args=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run):raise ValueError('Invalid run id')
    staging=Path('out/works/music/.ensemble-transfers');staging.mkdir(parents=True,exist_ok=True)
    work=args.resume or Path(tempfile.mkdtemp(prefix='chunks-',dir=staging))
    if args.resume:
        manifest=json.loads((work/'transfer.json').read_text());remote=manifest['archive']
        if not re.fullmatch(r'/work/gen/ensemble-exports/'+re.escape(args.run)+r'-[0-9]+\.tar\.gz',remote):
            raise ValueError('Transfer does not belong to this run')
    else:
        remote=f'/work/gen/ensemble-exports/{args.run}-{time.time_ns()}.tar.gz'
        result=subprocess.check_output(KUBE+['/work/venv/bin/python','-c',SNAPSHOT,f'/work/gen/{args.run}',remote],timeout=180)
        manifest=json.loads(result);(work/'transfer.json').write_text(json.dumps(manifest,indent=2))
    offset=0;archive=work/'works.tar.gz';whole=hashlib.sha256()
    with archive.open('wb') as output:
        for index,chunk in enumerate(manifest['chunks']):
            path=work/f'{index:05d}.chunk'
            for attempt in range(3):
                if path.exists():
                    data=path.read_bytes()
                    if len(data)==chunk['size'] and hashlib.sha256(data).hexdigest()==chunk['sha256']:
                        break
                try:
                    with path.open('wb') as f:
                        subprocess.run(KUBE+['/work/venv/bin/python','-c',READ,remote,str(offset),str(chunk['size'])],stdout=f,check=True,timeout=45)
                    data=path.read_bytes()
                    if len(data)!=chunk['size'] or hashlib.sha256(data).hexdigest()!=chunk['sha256']:
                        raise ValueError(f'Chunk {index} checksum mismatch')
                    break
                except (subprocess.SubprocessError,ValueError):
                    if attempt==2:raise
            output.write(data);whole.update(data);offset+=len(data)
            print(f'Verified chunk {index+1}/{len(manifest["chunks"])}',flush=True)
    if whole.hexdigest()!=manifest['sha256']:raise ValueError('Archive checksum mismatch')
    files=work/'files';files.mkdir()
    with tarfile.open(archive) as tar:tar.extractall(files,filter='data')
    for record in sorted(files.rglob('render.json')):
        source=record.parent;data=json.loads(record.read_text());target=args.out/source.relative_to(files)
        for name,digest in data['artifacts'].items():
            if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise ValueError(source/name)
        if target.exists():
            old=json.loads((target/'render.json').read_text())
            if old['artifacts']!=data['artifacts']:raise FileExistsError(f'Preserved different existing work: {target}')
            for name,digest in old['artifacts'].items():
                if hashlib.sha256((target/name).read_bytes()).hexdigest()!=digest:raise ValueError(target/name)
        else:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(source,target)
        print('Verified',target,flush=True)
    args.out.mkdir(parents=True,exist_ok=True)
    for report in files.glob('run-*.json'):shutil.copy2(report,args.out/report.name)


if __name__=='__main__':main()
