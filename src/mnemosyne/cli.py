"""Inspect the atelier, export retained works, and restore through versioned decoders."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile


def export_local(source, output):
    os.umask(0o077)
    source, output = source.resolve(), output.resolve()
    if output == source or source in output.parents:
        raise ValueError('export destination must be outside source')
    if not source.is_dir():
        raise ValueError('source must be an existing works directory')
    files = sorted(source.rglob('*'))
    if any(p.is_symlink() for p in files):
        raise ValueError('works export refuses symlinks')
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for path in files:
        if path.is_file():
            relative = path.relative_to(source)
            dest = output/relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            hashes[relative.as_posix()] = hashlib.sha256(dest.read_bytes()).hexdigest()
    (output/'export-manifest.json').write_text(json.dumps(hashes, indent=2)+'\n')
    return len(hashes)


def export_s3(uri, output, endpoint=None):
    import boto3
    from urllib.parse import urlsplit
    parsed = urlsplit(uri)
    prefix = parsed.path.lstrip('/').rstrip('/')+'/'
    s3 = boto3.client('s3', endpoint_url=endpoint)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for page in s3.get_paginator('list_objects_v2').paginate(Bucket=parsed.netloc, Prefix=prefix):
            for entry in page.get('Contents', []):
                rel = Path(entry['Key'][len(prefix):])
                if rel.is_absolute() or '..' in rel.parts or not rel.parts:
                    raise ValueError('unsafe S3 object name')
                target = root/rel
                target.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(parsed.netloc, entry['Key'], str(target))
        return export_local(root, output)


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == 'restore':
        from .restore import main as restore
        return restore(argv[1:])
    if argv and argv[0] == 'view':
        from .viewer import main as view
        return view(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('restore', help='decode works and optionally apply; see mnemo restore --help')
    commands.add_parser('view', help='read the atelier history in the console or export a site; see mnemo view --help')
    keys = commands.add_parser('keys').add_subparsers(dest='action', required=True)
    new = keys.add_parser('new', help="create the owner's key (keep offline) and the atelier's key (for the cluster)")
    new.add_argument('--output', type=Path, required=True)
    status = commands.add_parser('status')
    works = commands.add_parser('works').add_subparsers(dest='action', required=True)
    listing = works.add_parser('list')
    export = works.add_parser('export')
    for sub in (status, listing, export):
        sub.add_argument('--namespace', default='mnemosyne')
        sub.add_argument('--kubeconfig', type=Path)
        sub.add_argument('--context')
    export.add_argument('--source', default='/works', help='Mounted PVC directory, pod path or s3://bucket/prefix')
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--pod', help='Export from an existing studio pod over kubectl exec')
    export.add_argument('--endpoint', help='S3-compatible endpoint')
    args = parser.parse_args(argv)
    if args.command == 'keys':
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from .weave.backup import write_new
        args.output.mkdir(parents=True, exist_ok=True)
        owner, atelier = X25519PrivateKey.generate(), X25519PrivateKey.generate()
        write_new(args.output/'owner.key', owner.private_bytes_raw())
        write_new(args.output/'atelier.key', atelier.private_bytes_raw())
        public = owner.public_key().public_bytes_raw().hex()
        print(json.dumps({'owner_key': str(args.output/'owner.key'), 'keep': 'offline; needed only to restore',
                          'atelier_key': str(args.output/'atelier.key'), 'cluster_secret': 'atelier.key',
                          'ownerPublic': public}))
        return
    kube = ['kubectl']
    if args.kubeconfig:
        kube += ['--kubeconfig', str(args.kubeconfig)]
    if args.context:
        kube += ['--context', args.context]
    kube += ['--namespace', args.namespace]
    if args.command == 'status' or args.action == 'list':
        resource = 'ateliers.mnemosyne.art' if args.command == 'status' else 'opera.mnemosyne.art'
        subprocess.run(kube + ['get', resource, '-o', 'wide'], check=True)
        return
    if args.pod:
        with tempfile.TemporaryDirectory() as tmp:
            bundle, root = Path(tmp)/'export.tar', Path(tmp)/'works'
            root.mkdir()
            with bundle.open('wb') as stream:
                subprocess.run(kube+['exec', args.pod, '--', 'tar', '-C', args.source, '-cf', '-', '.'],
                               stdout=stream, check=True)
            with tarfile.open(bundle) as tar:
                for member in tar.getmembers():
                    if not (member.isfile() or member.isdir()):
                        raise ValueError('export contains nonregular files')
                tar.extractall(root, filter='data')
            count = export_local(root, args.output)
    elif args.source.startswith('s3://'):
        count = export_s3(args.source, args.output, args.endpoint)
    else:
        count = export_local(Path(args.source), args.output)
    print(json.dumps({'output': str(args.output), 'files': count}))
