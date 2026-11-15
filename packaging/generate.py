"""Generate dashboard schema and the recipe's owned CRD inventory from the core."""
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_BUILD = 2  # Raise when changing published package content.
app = ROOT / 'packaging/cozystack/apps/mnemosyne'
core = json.loads((ROOT / 'charts/mnemosyne/values.schema.json').read_text())
a = core['properties']['addon']['properties']
values = yaml.safe_load((app / 'values.yaml').read_text())

def infer(value):
    if isinstance(value, bool): return {'type': 'boolean', 'default': value}
    if isinstance(value, int): return {'type': 'integer', 'default': value}
    if isinstance(value, str): return {'type': 'string', 'default': value}
    if isinstance(value, list): return {'type': 'array', 'items': {'type': 'object'}, 'default': value}
    return {'type': 'object', 'properties': {k: infer(v) for k, v in value.items()}}

schema = infer(values)
schema['title'] = 'Mnemosyne atelier'
p = schema['properties']
for key in ('images', 'window', 'imagePullSecrets'):
    p[key] = a[key]
p['imagePullSecrets'] = {'type': 'array', 'items': {'type': 'object', 'required': ['name'], 'properties': {'name': {'type': 'string'}}}}
p['mode']['enum'] = ['chamber', 'background']
p['window']['properties']['kind']['enum'] = ['night', 'weekends', 'always']
p['models'] = {'type': 'object', 'x-kubernetes-preserve-unknown-fields': True}
p['resources'] = {'type': 'object', 'additionalProperties': {'type': 'string'}, 'description': 'Flat limits; cozy-lib derives requests using platform allocation ratios.'}
p['resourcesPreset']['enum'] = ['s1.small', 's1.medium', 's1.large', 'u1.small', 'u1.medium']
p['storageClass']['x-cozystack-options'] = {'source': 'storageclass'}
p['storageClass']['description'] = 'Empty uses the tenant default storage class.'
p['enabled']['description'] = 'Requires real image digests and a recipient key.'
p['suspend']['description'] = 'Keep work paused until the owner enables execution.'
p['s3']['description'] = 'Existing tenant Bucket endpoint and bucket name; credentials are mounted by reference, never queried by this chart.'
(app / 'values.schema.json').write_text(json.dumps(schema, indent=2) + '\n')
definition = {
    'apiVersion': 'cozystack.io/v1alpha1', 'kind': 'ApplicationDefinition',
    'metadata': {'name': 'mnemosyne'}, 'spec': {
        'application': {'kind': 'Mnemosyne', 'plural': 'mnemosynes', 'singular': 'mnemosyne', 'openAPISchema': json.dumps(schema)},
        'release': {'prefix': 'mnemosyne-', 'labels': {'sharding.fluxcd.io/key': 'tenants'},
                    'chartRef': {'kind': 'ExternalArtifact', 'name': 'mnemosyne-application-default-mnemosyne', 'namespace': 'cozy-system'}},
        'dashboard': {'singular': 'Mnemosyne atelier', 'plural': 'Mnemosyne ateliers', 'category': 'PaaS',
                      'description': 'Retained works and tenant-scoped backups', 'tags': ['art', 'backup'],
                      'tabs': ['workloads', 'yaml'],
                      'keysOrder': [['spec', k] for k in values]},
        'secrets': {'include': [], 'exclude': [{}]},
    }}
(ROOT / 'packaging/cozystack/system/mnemosyne-rd/cozyrds/mnemosyne.yaml').write_text(yaml.safe_dump(definition, sort_keys=False))
crds = list(yaml.safe_load_all((ROOT / 'charts/mnemosyne/crds/mnemosyne.yaml').read_text()))
recipe = {
    'apiVersion': 'kubepkg.dev/v1', 'kind': 'Recipe',
    'metadata': {'name': 'mnemosyne', 'annotations': {'kubepkg.dev/description': 'Mnemosyne portable atelier and retained works', 'kubepkg.dev/home': 'https://github.com/tym83/mnemosyne'}},
    'spec': {'version': yaml.safe_load((ROOT / 'charts/mnemosyne/Chart.yaml').read_text())['version'],
             'build': PACKAGE_BUILD, 'sources': {'core': {'dir': 'charts/mnemosyne'}},
             'charts': {'mnemosyne': {'from': ['core']}},
             'package': {'provides': ['mnemosyne', 'api:mnemosyne.art/v1alpha1'],
                         'crds': [c['metadata']['name'] for c in crds], 'images': [],
                         'rollback': {'safe': False},
                         'variants': [{'name': 'default', 'components': [{'name': 'mnemosyne', 'path': 'mnemosyne',
                             'install': {'namespace': 'mnemosyne', 'releaseName': 'mnemosyne', 'upgradeCRDs': 'CreateReplace',
                                         'readyWhen': [{'apiVersion': 'apiextensions.k8s.io/v1', 'kind': 'CustomResourceDefinition',
                                                        'name': c['metadata']['name'], 'condition': 'Established'} for c in crds]}}]}]}}}
(ROOT / 'packaging/kubepkg/recipe.yaml').write_text('# Staging recipe: prepare.py supplies the core and release image pins.\n' + yaml.safe_dump(recipe, sort_keys=False))
