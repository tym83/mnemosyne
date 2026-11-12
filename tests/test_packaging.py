"""Render boundaries: platform values must never grant cross-tenant access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
COZY = Path(os.environ.get('COZYSTACK_CHECKOUT', str(Path.home() / 'projects/cozystack')))

@unittest.skipUnless(shutil.which('helm') and (COZY / 'packages/library/cozy-lib').exists(), 'helm and read-only cozy-lib checkout required')
class Packaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.app = cls.root / 'app'
        shutil.copytree(ROOT / 'packaging/cozystack/apps/mnemosyne', cls.app)
        shutil.copytree(COZY / 'packages/library/cozy-lib', cls.app / 'charts/cozy-lib')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, chart, values=None, namespace='tenant-one', ok=True):
        path = self.root / 'values.yaml'
        path.write_text(yaml.safe_dump(values or {}))
        result = subprocess.run(['helm', 'template', 'mnemosyne-test', str(chart), '-n', namespace, '-f', str(path)], capture_output=True, text=True)
        if not ok:
            self.assertNotEqual(result.returncode, 0)
            return result.stderr
        self.assertEqual(result.returncode, 0, result.stderr)
        return [x for x in yaml.safe_load_all(result.stdout) if x]

    def active(self, namespace='tenant-one', mode='background'):
        # Render fixtures only. These hashes identify no published image.
        app = self.render(self.app, {'enabled': True, 'mode': mode, 'keySecretName': 'atelier', 'ownerPublicKey': '00' * 32,
            'images': {r: {'digest': 'sha256:' + 'a' * 64} for r in ('controller', 'studio')}}, namespace)
        return next(x['spec']['values'] for x in app if x['kind'] == 'HelmRelease')

    def test_inactive_defaults_and_dashboard(self):
        docs = self.render(self.app)
        hr = next(x for x in docs if x['kind'] == 'HelmRelease')
        self.assertFalse(hr['spec']['values']['addon']['enabled'])
        self.assertEqual(hr['spec']['install']['crds'], 'Skip')
        self.assertEqual(hr['spec']['upgrade']['crds'], 'Skip')
        monitor = next(x for x in docs if x['kind'] == 'WorkloadMonitor')
        self.assertEqual(monitor['spec']['replicas'], 0)
        subjects = next(x for x in docs if x['kind'] == 'RoleBinding')['subjects']
        self.assertIn('tenant-one-view', [s['name'] for s in subjects])
        self.assertNotIn('tenant-two-view', [s['name'] for s in subjects])

    def test_namespace_isolation_and_retention(self):
        for ns in ('tenant-one', 'tenant-two'):
            values = self.active(ns)
            docs = self.render(ROOT / 'charts/mnemosyne', values, ns)
            forbidden = {'ClusterRole', 'ClusterRoleBinding', 'PriorityClass', 'ResourceQuota', 'CustomResourceDefinition'}
            self.assertFalse(forbidden & {x['kind'] for x in docs})
            atelier = next(x for x in docs if x['kind'] == 'Atelier')
            self.assertEqual(atelier['spec']['runtime']['snapshotNamespace'], ns)
            for role in (x for x in docs if x['kind'] == 'Role'):
                for rule in role['rules']:
                    self.assertNotIn('nonResourceURLs', rule)
                    self.assertFalse({'namespaces', 'secrets', 'customresourcedefinitions', '*'} & set(rule.get('resources', [])))
            for binding in (x for x in docs if x['kind'] == 'RoleBinding'):
                self.assertEqual(binding['roleRef']['kind'], 'Role')
                self.assertTrue(all(s['namespace'] == ns for s in binding['subjects']))
            pvc = next(x for x in docs if x['kind'] == 'PersistentVolumeClaim')
            self.assertEqual(pvc['metadata']['annotations']['helm.sh/resource-policy'], 'keep')

    def test_namespace_guards(self):
        for field, value, message in [('snapshotNamespace', 'tenant-other', 'snapshotNamespace'), ('priorityClassName', '', 'priorityClassName'), ('window', {'kind': 'idle'}, 'idle detection')]:
            values = self.active()
            values['addon'][field] = value
            self.assertIn(message, self.render(ROOT / 'charts/mnemosyne', values, ok=False))

    def test_owner_has_no_artistic_inputs(self):
        # Chamber composes by itself; the owner supplies infrastructure only.
        docs = self.render(ROOT / 'charts/mnemosyne', self.active(mode='chamber'))
        config = next(d for d in docs if d['kind'] == 'ConfigMap' and 'runtime.json' in d['data'])
        runtime = json.loads(config['data']['runtime.json'])
        for key in ('commissions', 'climate', 'inner'):
            self.assertNotIn(key, json.dumps(runtime))
        from mnemosyne.operator.schema import RUNTIME
        self.assertFalse({'commissions', 'climate', 'inner'} & set(RUNTIME['properties']))
        self.assertNotIn('x-kubernetes-preserve-unknown-fields', RUNTIME)

    def test_digest_required_and_scope_enum(self):
        values = self.active()
        values['addon']['images']['studio']['digest'] = 'latest'
        self.render(ROOT / 'charts/mnemosyne', values, ok=False)
        values = self.active()
        values['addon']['rbacScope'] = 'typo'
        self.render(ROOT / 'charts/mnemosyne', values, ok=False)

    def test_storage_and_s3_references(self):
        docs = self.render(self.app, {'storageClass': 'tenant-storage', 'existingClaim': 'retained',
            's3': {'bucket': 'tenant-bucket', 'endpoint': 'https://s3.example.test', 'credentialsSecretName': 'bucket-access'}})
        values = next(x['spec']['values'] for x in docs if x['kind'] == 'HelmRelease')['addon']
        self.assertEqual(values['artifacts']['storageClass'], 'tenant-storage')
        self.assertEqual(values['artifacts']['existingClaim'], 'retained')
        self.assertEqual(values['artifacts']['s3']['prefix'], 'tenant-one/mnemosyne-test')
        self.assertEqual(values['env'][0]['valueFrom']['secretKeyRef']['name'], 'bucket-access')
        self.assertNotIn('Secret', {d['kind'] for d in docs})

    def test_resource_presets_and_schema_match(self):
        resources = self.active()['addon']['resources']
        self.assertEqual(resources['limits']['memory'], '2Gi')
        self.assertEqual(resources['requests']['cpu'], '0.1')
        definition = yaml.safe_load((ROOT / 'packaging/cozystack/system/mnemosyne-rd/cozyrds/mnemosyne.yaml').read_text())
        self.assertEqual(json.loads(definition['spec']['application']['openAPISchema']), json.loads((self.app / 'values.schema.json').read_text()))

    def test_recipe_owns_all_crds(self):
        recipe = yaml.safe_load((ROOT / 'packaging/kubepkg/recipe.yaml').read_text())
        shipped = {x['metadata']['name'] for x in yaml.safe_load_all((ROOT / 'charts/mnemosyne/crds/mnemosyne.yaml').read_text())}
        package = recipe['spec']['package']
        self.assertEqual(set(package['crds']), shipped)
        self.assertFalse(package['rollback']['safe'])
        ready = package['variants'][0]['components'][0]['install']['readyWhen']
        self.assertEqual({r['name'] for r in ready}, shipped)

    def test_platform_admin_grant(self):
        docs = self.render(ROOT / 'packaging/cozystack/system/mnemosyne-rd')
        role = next(x for x in docs if x['kind'] == 'ClusterRole')
        self.assertEqual(role['metadata']['labels'], {'rbac.cozystack.io/aggregate-to-tenant-admin': 'true'})
        self.assertEqual(role['rules'], [{'apiGroups': ['apps.cozystack.io'], 'resources': ['mnemosynes'], 'verbs': ['create', 'update', 'patch', 'delete']}])

if __name__ == '__main__':
    unittest.main()
