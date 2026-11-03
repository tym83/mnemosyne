"""Transfer a completed symphony in verified chunks; retain archives and drafts."""
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
from fetch_ensembles import KUBE, READ

SNAPSHOT = r'''
import hashlib,json,sys,tarfile
from pathlib import Path
source=Path(sys.argv[1]);archive=Path(sys.argv[2]);archive.parent.mkdir(parents=True,exist_ok=True)
manifest=json.loads((source/'work.json').read_text())
with tarfile.open(archive,'w:gz') as tar:
 for name,digest in manifest['artifacts'].items():
  path=source/name
  if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError(path)
  tar.add(path,arcname=name,recursive=False)
 tar.add(source/'work.json',arcname='work.json',recursive=False)
chunks=[];whole=hashlib.sha256()
with archive.open('rb') as f:
 while data:=f.read(1024*1024):
  whole.update(data);chunks.append({'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
print(json.dumps({'archive':str(archive),'sha256':whole.hexdigest(),'chunks':chunks}))
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run):raise ValueError('invalid run')
    staging=Path('out/works/music/.symphony-transfers');staging.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='transfer-',dir=staging))
    remote=f'/work/gen/symphony-exports/{args.run}-{time.time_ns()}.tar.gz'
    manifest=json.loads(subprocess.check_output(KUBE+['/work/venv/bin/python','-c',SNAPSHOT,
        f'/work/gen/{args.run}',remote],timeout=180))
    (work/'transfer.json').write_text(json.dumps(manifest,indent=2))
    offset=0;whole=hashlib.sha256();archive=work/'work.tar.gz'
    with archive.open('wb') as out:
        for i,chunk in enumerate(manifest['chunks']):
            for attempt in range(3):
                try:
                    data=subprocess.check_output(KUBE+['/work/venv/bin/python','-c',READ,remote,
                        str(offset),str(chunk['size'])],timeout=45)
                    if len(data)!=chunk['size'] or hashlib.sha256(data).hexdigest()!=chunk['sha256']:
                        raise ValueError('chunk checksum mismatch')
                    break
                except (subprocess.SubprocessError,ValueError):
                    if attempt==2:raise
            out.write(data);whole.update(data);offset+=len(data)
            print(f'Verified chunk {i+1}/{len(manifest["chunks"])}',flush=True)
    if whole.hexdigest()!=manifest['sha256']:raise ValueError('archive checksum mismatch')
    files=work/'files';files.mkdir()
    with tarfile.open(archive) as tar:tar.extractall(files,filter='data')
    data=json.loads((files/'work.json').read_text())
    for name,digest in data['artifacts'].items():
        if hashlib.sha256((files/name).read_bytes()).hexdigest()!=digest:raise ValueError(name)
    if args.out.exists():raise FileExistsError(f'preserved existing work: {args.out}')
    args.out.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(files,args.out)
    print(f'Verified {len(data["artifacts"])} artifacts: {args.out}')


if __name__=='__main__':main()
