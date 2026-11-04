"""Pod-only transport/API integration check, NOT the artistic acceptance test.

Source is state_manifests.py output. Carrier cells are synthetic test fixtures,
not school pieces. Losing works means copying only a seeded surviving subset;
no original files are deleted. Run with a new --output directory.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from scheherazade.restore import Kubectl, read_archive
from scheherazade.state.collect import archive, normalize
from scheherazade.weave import registry
from scheherazade.weave.backup import write_new
from scheherazade.weave.codecs.v1 import fountain, payload, surface


def includes(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and includes(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        # API admission may add list entries (e.g. a not-ready Node taint).
        # Retention is a subsequence check; exact equality is reported separately.
        if not isinstance(actual, list):
            return False
        remaining = iter(actual)
        return all(any(includes(item, value) for item in remaining) for value in expected)
    return actual == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'kubeconfig'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--context', required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    data = archive(yaml.safe_load_all(args.source.read_text()))
    expected = read_archive(data)
    write_new(args.output / 'source.tar.zst', data)
    key = X25519PrivateKey.generate()
    keyfile = args.output / 'recipient.key'
    write_new(keyfile, key.private_bytes_raw())
    root = ET.Element('score-partwise')
    part = ET.SubElement(root, 'part', id='P1')
    for i in range(600):
        m = ET.SubElement(part, 'measure', number=str(i+1))
        if i == 0:
            ET.SubElement(ET.SubElement(m, 'attributes'), 'divisions').text = '120'
        m.extend(surface.notes((('A', 0, 2), ('E', 0, 3), ('G', 0, 3)), 120, 120, '3'))
    source = args.output / 'transport-fixture.xml'
    surface.write(root, source)
    capacity = surface.capacity(root) - 36
    envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
    encoder = fountain.Encoder(envelope, capacity, key)
    count = fountain.recommended_count(len(envelope), capacity)
    lost = math.ceil(count * .3)
    surviving = random.Random(20261103).sample(range(count), count - lost)
    works = args.output / 'surviving-fixtures'
    works.mkdir()
    for i in surviving:
        registry.encode_fountain(source, works / f'{i:06d}.musicxml', encoder.frame(i), key)
    restored = args.output / 'restored'
    command = [sys.executable, '-m', 'scheherazade.restore', '--works', str(works),
               '--key', str(keyfile), '--output', str(restored), '--apply',
               '--kubeconfig', str(args.kubeconfig), '--context', args.context]
    with (args.output / 'restore.log').open('x') as log:
        subprocess.run(command, stdout=log, stderr=log, check=True)
    if (restored / 'archive.tar.zst').read_bytes() != data:
        raise RuntimeError('archive differs from source')
    api = Kubectl(args.kubeconfig, args.context)
    equal = contained = 0
    for obj in expected:
        base, resource = api.resource(obj['apiVersion'], obj['kind'])
        if resource['namespaced']:
            base += '/namespaces/' + obj['metadata']['namespace']
        actual = normalize(api.run(['get', '--raw', base + '/' + resource['name'] + '/' + obj['metadata']['name']]))
        equal += actual == obj
        contained += includes(actual, obj)
    result = {'scope': 'synthetic transport fixtures, not artistic acceptance',
              'objects': len(expected), 'works': count, 'omitted': lost, 'surviving': len(surviving),
              'archive_identical': True, 'sha256': hashlib.sha256(data).hexdigest(),
              'objects_equal_ignoring_server_fields': equal, 'objects_preserving_all_source_fields': contained}
    write_new(args.output / 'result.json', json.dumps(result, indent=2).encode())
    print(json.dumps(result))
    if contained != len(expected):
        raise RuntimeError('source fields differ after restore')


if __name__ == '__main__':
    main()
