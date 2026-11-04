"""Discover and collect Kubernetes state, or canonicalize manifest YAML."""
import argparse
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.parse import quote

import yaml
import zstandard

SKIP = {('', 'events'), ('events.k8s.io', 'events'),
        ('coordination.k8s.io', 'leases'), ('', 'endpoints'),
        ('discovery.k8s.io', 'endpointslices'), ('', 'componentstatuses')}
VOLATILE = {'managedFields', 'uid', 'resourceVersion', 'creationTimestamp',
            'deletionTimestamp', 'deletionGracePeriodSeconds', 'selfLink', 'generation'}


def secret_resource(kind):
    # Aggregated APIs can expose credentials under kinds such as TenantSecret.
    return 'secret' in kind.lower()


def normalize(obj, *, include_secrets=False):
    """Strip server bookkeeping, retaining desired state and reference identities."""
    obj = deepcopy(obj)
    group = obj['apiVersion'].rsplit('/', 1)[0] if '/' in obj['apiVersion'] else ''
    kind = obj['kind']
    if (secret_resource(kind) and not include_secrets) or (
        (group, kind) in {('', 'Event'), ('events.k8s.io', 'Event'),
                         ('coordination.k8s.io', 'Lease'), ('', 'Endpoints'),
                         ('discovery.k8s.io', 'EndpointSlice'), ('', 'ComponentStatus')}):
        return None
    owners = obj.get('metadata', {}).get('ownerReferences', [])
    if (kind == 'Pod' and group == '' and any(r.get('controller') for r in owners)
            or kind == 'ReplicaSet' and group == 'apps'
            and any(r.get('controller') and r.get('kind') == 'Deployment' for r in owners)):
        return None
    obj.pop('status', None)
    # Also normalize embedded PodTemplate metadata, without altering arbitrary
    # application data dictionaries (e.g. ConfigMap data or CR spec.status).
    def metadata(value):
        for field in VOLATILE:
            value.pop(field, None)
        annotations = value.get('annotations', {})
        annotations.pop('kubectl.kubernetes.io/last-applied-configuration', None)
        if 'annotations' in value and not annotations:
            value.pop('annotations')
    metadata(obj.setdefault('metadata', {}))
    if group in ('', 'apps', 'batch'):
        spec = obj.get('spec') or {}
        for template in (spec.get('template', {}),
                         spec.get('jobTemplate', {}).get('spec', {}).get('template', {})):
            if template and 'metadata' in template:
                metadata(template['metadata'])
    return obj


def archive(objects, *, include_secrets=False):
    """Canonical YAML members in a sorted, fixed-header USTAR, compressed by zstd."""
    members = {}
    for source in objects:
        obj = normalize(source, include_secrets=include_secrets)
        if obj is None:
            continue
        identity = [obj['apiVersion'], obj['kind'], obj['metadata'].get('namespace', ''),
                    obj['metadata']['name']]
        # Hash names avoid path traversal and USTAR name length limits for CRs.
        name = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest() + '.yaml'
        if name in members:
            raise ValueError(f'duplicate object: {identity}')
        members[name] = yaml.safe_dump(obj, sort_keys=True, allow_unicode=True).encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
    return zstandard.ZstdCompressor(level=9, write_checksum=True).compress(stream.getvalue())


def collect(api, *, namespace=None, include_secrets=False):
    """GET only. Scoped mode never lists cluster objects or other namespaces.

    Every discovery/list failure is fatal; no best-effort incomplete snapshots.
    API list pagination is supported. Different resource lists are not atomic.
    """
    def get(path, params=()):
        request = api.param_serialize('GET', path, query_params=list(params),
                                      header_params={'Accept': 'application/json'},
                                      auth_settings=['BearerToken'])
        response = api.call_api(*request, _request_timeout=(10, 60))
        response.read()
        if response.status != 200:
            raise RuntimeError(f'GET {path}: HTTP {response.status}; snapshot aborted')
        return json.loads(response.data)
    versions = [('/api/' + v, '') for v in get('/api')['versions']]
    for group in sorted(get('/apis')['groups'], key=lambda g: g['name']):
        preferred = group['preferredVersion']['groupVersion']
        for version in sorted(group['versions'], key=lambda v: (v['groupVersion'] != preferred, v['groupVersion'])):
            versions.append(('/apis/' + version['groupVersion'], group['name']))
    seen = set()
    objects = []
    for base, group in versions:
        resources = get(base)['resources']
        for resource in sorted(resources, key=lambda r: r['name']):
            name = resource['name']
            identity = group, name
            if ('/' in name or not {'list', 'create'} <= set(resource.get('verbs') or [])
                    or identity in SKIP or identity in seen
                    or secret_resource(resource['kind']) and not include_secrets
                    or namespace is not None and not resource['namespaced']):
                continue
            seen.add(identity)
            path = base
            if namespace is not None:
                path += '/namespaces/' + quote(namespace, safe='')
            path += '/' + name
            token = ''
            tokens = set()
            while True:
                page = get(path, [('limit', 500), ('continue', token)])
                for item in page['items']:
                    item.setdefault('apiVersion', base.split('/', 2)[2])
                    item.setdefault('kind', resource['kind'])
                    if namespace is not None and item.get('metadata', {}).get('namespace') != namespace:
                        raise ValueError('API returned an object outside requested namespace')
                    objects.append(item)
                token = page.get('metadata', {}).get('continue', '')
                if not token:
                    break
                if token in tokens:
                    raise ValueError('repeated API pagination token')
                tokens.add(token)
    return objects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--kubeconfig', type=Path)
    source.add_argument('--manifests', type=Path)
    parser.add_argument('--context')
    parser.add_argument('--namespace')
    parser.add_argument('--include-secrets', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.manifests:
        objects = [o for o in yaml.safe_load_all(args.manifests.read_text()) if o is not None]
        if args.namespace:
            objects = [o for o in objects if o.get('metadata', {}).get('namespace') == args.namespace]
    else:
        from kubernetes import client, config
        with config.new_client_from_config(config_file=str(args.kubeconfig.expanduser()),
                                           context=args.context, persist_config=False) as api:
            objects = collect(api, namespace=args.namespace, include_secrets=args.include_secrets)
    data = archive(objects, include_secrets=args.include_secrets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # API manifests can contain credentials outside Secret resources as well.
    import os
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
        out.write(data)
    count = sum(normalize(o, include_secrets=args.include_secrets) is not None for o in objects)
    print(json.dumps({'objects': count, 'archive_bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest()}))


if __name__ == '__main__':
    main()
