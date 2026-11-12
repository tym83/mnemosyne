"""Regenerate the checked-in Helm schemas after changing values or API schemas."""
import json
from pathlib import Path
import yaml
from mnemosyne.atelier import crds
from mnemosyne.operator.schema import RUNTIME


def infer(value):
    if isinstance(value, bool): return {'type': 'boolean'}
    if isinstance(value, int): return {'type': 'integer'}
    if isinstance(value, str): return {'type': 'string'}
    if value is None: return {'type': ['string', 'null']}
    if isinstance(value, list): return {'type': 'array', 'items': infer(value[0]) if value else {}}
    return {'type': 'object', 'properties': {k: infer(v) for k,v in value.items()}}


chart = Path('charts/mnemosyne')
schema = infer(yaml.safe_load((chart/'values.yaml').read_text()))
schema['$schema'] = 'http://json-schema.org/draft-07/schema#'
a = schema['properties']['addon']['properties']
a['rbacScope'] = {'type': 'string', 'enum': ['cluster', 'namespace']}
for field in ('mode', 'window', 'inventory'):
    a[field] = RUNTIME['properties'][field]
for role in ('controller', 'studio'):
    a['images']['properties'][role]['properties']['digest']['pattern'] = '^$|^sha256:[a-f0-9]{64}$'
a['key']['properties']['provider'] = {'type': 'string', 'enum': ['file', 'vault', 'kms']}
a['controllerReplicas'] = {'const': 1}
a['deadlineSeconds'] = {'type': 'integer', 'minimum': 60}
schema['allOf'] = [{'if': {'properties': {'addon': {'properties': {'enabled': {'const': True}}}}},
    'then': {'properties': {'addon': {'properties': {'images': {'properties': {
        role: {'properties': {'digest': {'minLength': 71}}} for role in ('controller', 'studio')}}}}}}}]
(chart/'values.schema.json').write_text(json.dumps(schema, indent=2)+'\n')
(chart/'crds/mnemosyne.yaml').write_text(yaml.safe_dump_all(crds(), sort_keys=False))
