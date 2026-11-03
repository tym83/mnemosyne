import io
import json
import tarfile
import unittest
from copy import deepcopy
from types import SimpleNamespace

import yaml
import zstandard
from scheherazade.state.collect import archive, collect, normalize


def obj(kind='ConfigMap', name='test', api='v1', **fields):
    return dict(apiVersion=api, kind=kind,
                metadata={'name': name, 'namespace': 'tenant-scheherazade'}, **fields)


class FakeAPI:
    def __init__(self):
        self.calls = []
        self.pages = {
            '/api': {'versions': ['v1']},
            '/apis': {'groups': [{'name': 'example.org',
                'preferredVersion': {'groupVersion': 'example.org/v1'},
                'versions': [{'groupVersion': 'example.org/v1'}, {'groupVersion': 'example.org/v2'}]}]},
            '/api/v1': {'resources': [self.resource(n, k, ns) for n, k, ns in [
                ('secrets', 'Secret', True), ('configmaps', 'ConfigMap', True),
                ('events', 'Event', True), ('endpoints', 'Endpoints', True),
                ('tenantsecrets', 'TenantSecret', True),
                ('nodes', 'Node', False), ('pods/status', 'Pod', True)]]},
            '/apis/example.org/v1': {'resources': [self.resource('widgets', 'Widget', True)]},
            '/apis/example.org/v2': {'resources': [self.resource('widgets', 'Widget', True),
                                                    self.resource('extras', 'Extra', True)]},
        }

    def resource(self, name, kind, ns):
        return dict(name=name, kind=kind, namespaced=ns, verbs=['get', 'list', 'create'])

    def param_serialize(self, method, path, **kwargs):
        return method, path, kwargs

    def call_api(self, method, path, options, **kwargs):
        self.calls.append((method, path))
        page = self.pages.get(path)
        if page is None:
            page = {'items': [], 'metadata': {}}
            if path.endswith('/configmaps'):
                token = dict(options['query_params'])['continue']
                page = {'items': [obj(name='second' if token else 'first')],
                        'metadata': {} if token else {'continue': 'next'}}
        return SimpleNamespace(status=200, data=json.dumps(page).encode(), read=lambda: None)


class CollectTests(unittest.TestCase):
    def test_read_only_and_null_verbs_are_not_collected(self):
        api = FakeAPI()
        for name, verbs in [('metrics', ['get', 'list']), ('virtual', None)]:
            resource = api.resource(name, name, True)
            resource['verbs'] = verbs
            api.pages['/api/v1']['resources'].append(resource)
        collect(api, namespace='tenant-scheherazade')
        self.assertFalse(any(path.endswith(('/metrics', '/virtual')) for _, path in api.calls))

    def test_namespace_never_reads_secrets_or_cluster_objects(self):
        api = FakeAPI()
        result = collect(api, namespace='tenant-scheherazade')
        self.assertEqual(len(result), 2)
        for method, path in api.calls:
            self.assertEqual(method, 'GET')
            self.assertFalse(any(path.endswith('/' + x) for x in ('secrets', 'tenantsecrets', 'nodes', 'events', 'endpoints')))
            if path.count('/') > 3:
                self.assertIn('/namespaces/tenant-scheherazade/', path)
        self.assertIn(('GET', '/apis/example.org/v2/namespaces/tenant-scheherazade/extras'), api.calls)
        self.assertNotIn(('GET', '/apis/example.org/v2/namespaces/tenant-scheherazade/widgets'), api.calls)

    def test_full_scope_and_secret_opt_in(self):
        api = FakeAPI()
        collect(api, include_secrets=True)
        self.assertIn(('GET', '/api/v1/nodes'), api.calls)
        self.assertIn(('GET', '/api/v1/secrets'), api.calls)

    def test_fail_closed(self):
        api = FakeAPI()
        api.pages['/api/v1/namespaces/tenant-scheherazade/configmaps'] = {'items': [obj()]}
        api.pages['/api/v1/namespaces/tenant-scheherazade/configmaps']['items'][0]['metadata']['namespace'] = 'other'
        with self.assertRaises(ValueError):
            collect(api, namespace='tenant-scheherazade')
        api.call_api = lambda *a, **kw: SimpleNamespace(status=403, read=lambda: None)
        with self.assertRaisesRegex(RuntimeError, '403'):
            collect(api)

    def test_normalization_and_filtering(self):
        source = obj(data={'status': 'application data', 'uid': 'keep'})
        source['status'] = {'server': 'state'}
        source['metadata'].update(uid='old', resourceVersion='1', managedFields=[], creationTimestamp='now')
        original = deepcopy(source)
        normalized = normalize(source)
        self.assertEqual(source, original)
        self.assertNotIn('status', normalized)
        self.assertNotIn('uid', normalized['metadata'])
        self.assertEqual(normalized['data'], source['data'])
        for kind, api in [('Secret', 'v1'), ('Event', 'events.k8s.io/v1'),
                          ('Lease', 'coordination.k8s.io/v1'), ('Endpoints', 'v1'),
                          ('EndpointSlice', 'discovery.k8s.io/v1')]:
            self.assertIsNone(normalize(obj(kind, api=api)))
        self.assertIsNotNone(normalize(obj('Secret'), include_secrets=True))
        for kind, api, owner in [('Pod', 'v1', 'Job'), ('ReplicaSet', 'apps/v1', 'Deployment')]:
            item = obj(kind, api=api)
            self.assertIsNotNone(normalize(item))
            item['metadata']['ownerReferences'] = [{'kind': owner, 'controller': True}]
            self.assertIsNone(normalize(item))

    def test_canonical_archive(self):
        a, b = obj(name='a'), obj(name='b', data={'z': 'last', 'a': 'first'})
        first = archive([a, b, obj('Secret')])
        self.assertEqual(first, archive([dict(reversed(list(b.items()))), a]))
        with tarfile.open(fileobj=io.BytesIO(zstandard.ZstdDecompressor().decompress(first))) as tar:
            self.assertEqual(tar.getnames(), sorted(tar.getnames()))
            self.assertEqual(len(tar.getmembers()), 2)
            for member in tar:
                self.assertEqual((member.uid, member.gid, member.mtime), (0, 0, 0))
                self.assertEqual(yaml.safe_load(tar.extractfile(member))['kind'], 'ConfigMap')
        with self.assertRaises(ValueError):
            archive([a, a])
