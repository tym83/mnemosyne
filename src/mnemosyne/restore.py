"""Recover authenticated Kubernetes manifests from surviving MusicXML works."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time

import yaml
import zstandard
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from .state.collect import normalize, secret_resource
from .weave import DecodeError, registry
from .weave.backup import write_new
from .weave.codecs.v1 import fountain, frames

MAX_ARCHIVE = 128 * 1024 * 1024
CLUSTER_KINDS = {
    ('v1', 'Namespace'), ('v1', 'Node'), ('v1', 'PersistentVolume'),
    ('apiextensions.k8s.io/v1', 'CustomResourceDefinition'),
    ('rbac.authorization.k8s.io/v1', 'ClusterRole'),
    ('rbac.authorization.k8s.io/v1', 'ClusterRoleBinding'),
    ('storage.k8s.io/v1', 'StorageClass'), ('storage.k8s.io/v1', 'CSIDriver'),
    ('storage.k8s.io/v1', 'CSINode'), ('storage.k8s.io/v1', 'VolumeAttachment'),
    ('scheduling.k8s.io/v1', 'PriorityClass'), ('node.k8s.io/v1', 'RuntimeClass'),
    ('admissionregistration.k8s.io/v1', 'MutatingWebhookConfiguration'),
    ('admissionregistration.k8s.io/v1', 'ValidatingWebhookConfiguration'),
    ('apiregistration.k8s.io/v1', 'APIService'),
}


def identity(obj):
    return (obj['apiVersion'], obj['kind'], obj['metadata'].get('namespace', ''),
            obj['metadata']['name'])


def read_archive(data, *, include_secrets=False):
    """Read bounded regular members in memory, never extract paths to disk."""
    objects = []
    seen = set()
    try:
        if zstandard.frame_content_size(data) > MAX_ARCHIVE:
            raise ValueError('archive exceeds unpacked size limit')
        raw = zstandard.ZstdDecompressor().decompress(data, max_output_size=MAX_ARCHIVE,
                                                     allow_extra_data=False)
        if len(raw) > MAX_ARCHIVE:
            raise ValueError('archive exceeds unpacked size limit')
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
            for member in tar:
                if not member.isfile() or member.size > MAX_ARCHIVE:
                    raise ValueError('archive contains a nonregular or oversized member')
                obj = yaml.safe_load(tar.extractfile(member).read())
                ident = identity(obj)
                if not all(isinstance(v, str) for v in ident) or not all(ident[i] for i in (0, 1, 3)):
                    raise ValueError('invalid object identity')
                expected = hashlib.sha256(json.dumps(list(ident), separators=(',', ':')).encode()).hexdigest() + '.yaml'
                if member.name != expected or ident in seen:
                    raise ValueError('invalid member name or duplicate object')
                if secret_resource(obj['kind']) and not include_secrets:
                    raise ValueError('Secret resources are not supported by restore')
                if normalize(obj, include_secrets=include_secrets) != obj:
                    raise ValueError('archive contains noncanonical server state')
                seen.add(ident)
                objects.append(obj)
        if not objects:
            raise ValueError('archive is empty')
    except (KeyError, TypeError, AttributeError, tarfile.TarError, yaml.YAMLError,
            zstandard.ZstdError) as exc:
        raise ValueError('invalid Kubernetes state archive') from exc
    return objects


def recover_works(directory, key, *, include_secrets=False, at=None):
    """Try every XML; damaged/unsupported works are erasures, never plaintext."""
    groups = defaultdict(list)
    report = {'decoded': [], 'rejected': [], 'snapshots': []}
    for path in sorted(directory.rglob('*')):
        texts = path.name.endswith('.variants.json')
        if not path.is_file() or not (texts or path.suffix.lower() in ('.xml', '.musicxml')):
            continue
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                raise DecodeError('carrier exceeds size limit')
            if texts:
                from .weave import variants
                decoded = registry.Decoded('fountain-batch-v1', variants.decode_many(json.loads(path.read_text()), key))
            else:
                decoded = registry.decode(path, key)
            if decoded.transport in ('fountain-v1', 'fountain-batch-v1'):
                batch = decoded.frame if decoded.transport == 'fountain-batch-v1' else [decoded.frame]
                identities = [fountain.unpack(frame, key) for frame in batch]
                if not identities or len({(s, k, z, t) for s, i, k, z, t, v in identities}) != 1:
                    raise DecodeError('mixed or empty fountain batch')
                snapshot, _, k, size, total, _ = identities[0]
                group = ('fountain-v1', snapshot.hex(), k, size, total)
            elif decoded.transport == 'multipart-v1':
                f = decoded.frame
                group = ('multipart-v1', f['bundle'].hex(), f['count'], f['total'], f['chunk_size'])
            else:
                raise DecodeError('unsupported frame transport')
            if decoded.transport == 'fountain-batch-v1':
                groups[group].extend(decoded.frame)
            else:
                groups[group].append(decoded.frame)
            report['decoded'].append(str(path.relative_to(directory)))
        except (OSError, ValueError, IndexError, KeyError, TypeError, AttributeError):
            report['rejected'].append(str(path.relative_to(directory)))
    candidates = {}
    for group, fs in groups.items():
        try:
            if group[0] == 'fountain-v1':
                data = fountain.recover(fs, key)
            else:
                unique = {}
                for frame in fs:
                    if frame['index'] in unique and unique[frame['index']] != frame:
                        raise DecodeError('conflicting multipart frame')
                    unique[frame['index']] = frame
                data = frames.assemble(list(unique.values()), key)
            from .state.ledger import parse
            header, archive = parse(data)
            if header is None:
                read_archive(data, include_secrets=include_secrets)
            digest = hashlib.sha256(data).hexdigest()
            candidates[digest] = header, archive, data
            report['snapshots'].append({'id': group[1], 'complete': True, 'sha256': digest,
                                        **({'kind': header['kind'], 'at': header['at']} if header else {})})
        except ValueError:
            report['snapshots'].append({'id': group[1], 'complete': False})
    pieces = [(h, a) for h, a, _ in candidates.values() if h is not None]
    if pieces:
        # Cluster state over time: replay keyframe + deltas up to the chosen moment.
        from .state.ledger import replay
        data, objects, moment = replay(pieces, at)
        if include_secrets is False and any(secret_resource(o['kind']) for o in objects):
            raise ValueError('Secret resources are not supported by restore')
        report['moment'] = moment
        return data, objects, report
    candidates = {d: (data, read_archive(data, include_secrets=include_secrets))
                  for d, (_, _, data) in candidates.items()}
    if len(candidates) != 1:
        raise ValueError(f'expected one verified archive, found {len(candidates)}; '
                         f'decoded={len(report["decoded"])} rejected={len(report["rejected"])}; '
                         'separate snapshots or provide more readable works')
    data, objects = next(iter(candidates.values()))
    return data, objects, report


def ordered(objects):
    scopes = {key: False for key in CLUSTER_KINDS}
    for obj in objects:
        if identity(obj)[:2] == ('apiextensions.k8s.io/v1', 'CustomResourceDefinition'):
            spec = obj['spec']
            for version in spec['versions']:
                scopes[(spec['group'] + '/' + version['name'], spec['names']['kind'])] = spec['scope'] == 'Namespaced'
    def stage(obj):
        version, kind, namespace, _ = identity(obj)
        if (version, kind) == ('apiextensions.k8s.io/v1', 'CustomResourceDefinition'):
            return 0
        if (version, kind) == ('v1', 'Namespace'):
            return 1
        if namespace:
            if scopes.get((version, kind)) is False:
                raise ValueError('cluster-scoped object has a namespace')
            return 3
        if scopes.get((version, kind)) is True:
            raise ValueError(f'explicit namespace required: {version}/{kind}')
        return 2
    return sorted(objects, key=lambda obj: (stage(obj), identity(obj))), stage


class Kubectl:
    def __init__(self, kubeconfig, context):
        self.command = ['kubectl', '--kubeconfig', str(kubeconfig.expanduser()), '--context', context]

    def run(self, arguments, obj=None):
        result = subprocess.run(self.command + arguments, input=json.dumps(obj) if obj else None,
                                text=True, capture_output=True, timeout=90)
        if result.returncode:
            # stderr may quote credentials embedded in application manifests.
            raise RuntimeError(f'kubectl failed (exit {result.returncode}); response withheld')
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def resource(self, api_version, kind):
        base = '/api/v1' if api_version == 'v1' else '/apis/' + api_version
        resources = self.run(['get', '--raw', base])['resources']
        for resource in resources:
            if resource['kind'] == kind and '/' not in resource['name']:
                return base, resource
        raise RuntimeError('resource is not yet discoverable')

    def owner_uid(self, owner, namespace):
        from urllib.parse import quote
        base, resource = self.resource(owner['apiVersion'], owner['kind'])
        if resource['namespaced']:
            if not namespace:
                raise RuntimeError('namespaced owner of cluster-scoped resource')
            base += '/namespaces/' + quote(namespace, safe='')
        obj = self.run(['get', '--raw', base + '/' + resource['name'] + '/' + quote(owner['name'], safe='')])
        return obj['metadata']['uid']

    def apply(self, obj):
        _, resource = self.resource(obj['apiVersion'], obj['kind'])
        if resource['namespaced'] != bool(obj['metadata'].get('namespace')):
            raise RuntimeError('manifest namespace does not match API scope')
        self.run(['apply', '--server-side', '--field-manager=mnemosyne-restore',
                  '--request-timeout=60s', '-f', '-', '-o', 'json'], obj)
        if obj['kind'] == 'CustomResourceDefinition' and obj['apiVersion'] == 'apiextensions.k8s.io/v1':
            result = subprocess.run(self.command + ['wait', '--for=condition=Established',
                '--timeout=60s', 'crd/' + obj['metadata']['name']], capture_output=True, timeout=70)
            if result.returncode:
                raise RuntimeError('CRD did not become Established')


def apply_objects(objects, backend, *, attempts=5, delay=2):
    objects, stage = ordered(objects)
    applied = []
    for phase in range(4):
        pending = [obj for obj in objects if stage(obj) == phase]
        for attempt in range(attempts):
            remaining = []
            for source in pending:
                obj = deepcopy(source)
                try:
                    for owner in obj['metadata'].get('ownerReferences', []):
                        if secret_resource(owner['kind']):
                            raise ValueError('Secret owner references are unsupported')
                        owner['uid'] = backend.owner_uid(owner, obj['metadata'].get('namespace', ''))
                    backend.apply(obj)
                    applied.append(identity(obj))
                except (RuntimeError, subprocess.TimeoutExpired):
                    remaining.append(source)
            pending = remaining
            if not pending:
                break
            if attempt + 1 < attempts:
                time.sleep(delay)
        if pending:
            raise RuntimeError(f'apply phase {phase} failed after {attempts} attempts; '
                               f'applied={len(applied)}, pending={[identity(o) for o in pending]}; '
                               'earlier successful applies remain in the target')
    return applied


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--works', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--output', type=Path, help='New output directory; default: unique out/restore-*')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--include-secrets', action='store_true', help='Explicitly accept encrypted Secret resources from an owner-enabled snapshot')
    parser.add_argument('--kubeconfig', type=Path)
    parser.add_argument('--context')
    parser.add_argument('--dry-run', action='store_true', help='Verify and write manifests; never contact a cluster')
    parser.add_argument('--at', help='ISO moment: restore the newest complete state not after it (default: newest)')
    args = parser.parse_args(argv)
    if args.apply and not (args.kubeconfig and args.context):
        parser.error('--apply requires explicit --kubeconfig and --context')
    if not args.works.is_dir():
        parser.error('--works must be a directory')
    key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
    data, objects, report = recover_works(args.works, key, include_secrets=args.include_secrets, at=args.at)
    objects, stage = ordered(objects)
    if args.output:
        output = args.output
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
    else:
        Path('out').mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix='restore-', dir='out'))
    write_new(output / 'archive.tar.zst', data)
    write_new(output / 'manifests.yaml', yaml.safe_dump_all(objects, sort_keys=True).encode())
    report.update(sha256=hashlib.sha256(data).hexdigest(), objects=len(objects),
                  phases=[sum(stage(o) == i for o in objects) for i in range(4)],
                  dry_run=args.dry_run, applied=False)
    try:
        if args.apply and not args.dry_run:
            apply_objects(objects, Kubectl(args.kubeconfig, args.context))
            report['applied'] = True
    except Exception:
        report['apply_failed'] = True
        raise
    finally:
        write_new(output / 'report.json', json.dumps(report, indent=2).encode())
        print(json.dumps({'output': str(output), 'objects': len(objects),
                          'sha256': report['sha256'], 'applied': report['applied']}))


if __name__ == '__main__':
    main()
