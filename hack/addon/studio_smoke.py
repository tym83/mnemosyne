"""Run only in studio/CI: autonomous chamber nights, weave, decode, export, restore."""
import argparse
import json
from pathlib import Path
import shutil
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.operator.worker import run
from mnemosyne.cli import export_local
from mnemosyne.restore import recover_works
from mnemosyne.state.ledger import Ledger, members, pack

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
p.add_argument('--snapshot', type=Path, required=True)
p.add_argument('--render', action='store_true')
p.add_argument('--nights', type=int, default=60)
a = p.parse_args()
request = {'mode': 'chamber', 'render': a.render, 'atelier': 'technical-smoke'}
objects = json.loads(a.snapshot.read_text())
key = X25519PrivateKey.generate()
previous, nights = None, []
for night in range(a.nights):
    root = a.output/f'night-{night:03d}'
    records, report = run(request, root, key, objects, previous=previous)
    previous = json.loads((root/'lineage.json').read_text())
    nights.append(root)
    if not Ledger(a.output/'ledger').pending():
        break
else:
    raise RuntimeError('cluster state still pending after all nights')
export = a.output/'export'
export.mkdir()
for root in nights:
    if (root/'woven').exists():
        export_local(root/'woven', export/root.name)
expected = pack(members(objects))
assert recover_works(export, key)[0] == expected
# Lose 30% of the woven works; restore from scores alone.
works = sorted(p for p in export.rglob('*') if p.name.endswith(('.musicxml', '.variants.json', '.audience.json')))
survivors = a.output/'survivors'
survivors.mkdir()
for path in works[:len(works) - len(works)*3//10]:
    shutil.copyfile(path, survivors/f'{path.parent.name}-{path.name}')
assert recover_works(survivors, key)[0] == expected
print(json.dumps({'nights': len(nights), 'works': len(works), 'objects': len(members(objects)),
                  'export_recovered': True, 'survived_loss': .3}), flush=True)
