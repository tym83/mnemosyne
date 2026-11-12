"""An atelier's history as one archive: lived elsewhere, continued in a cluster.

export packs an atelier directory (lineage.json, translations.json and the
nights with their works, notebooks, carriers and the ledger) into a tar.gz in
the layout the studio keeps on its volume:

  lineage.json  translations.json  ledger/  <night>/...

import unpacks it into an empty atelier directory on the volume, after the
archive's sha256 is checked; it never overwrites a living atelier. Keys never
travel in the archive: the atelier key is a Secret, the owner's key stays out.

  mnemo history export --root out/year/leonia-year --out leonia-history.tar.gz
  mnemo history import --source https://.../leonia-history.tar.gz --sha256 HEX --into /works/NAME
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

TOP = ('lineage.json', 'translations.json', 'year.jsonl')
NEVER = ('keys', 'site', 'site2', 'restore-try')


def members(root: Path):
    """(path on disk, path in the archive) for everything that belongs to the history."""
    root = Path(root)
    for name in TOP:
        if (root/name).is_file():
            yield root/name, name
    nights = root/'nights' if (root/'nights').is_dir() else root
    for path in sorted(nights.rglob('*')):
        rel = path.relative_to(nights)
        if path.is_file() and rel.parts[0] not in NEVER + TOP and not path.name.endswith('.tmp') \
                and not (nights == root and len(rel.parts) == 1):
            yield path, str(rel)


def export(root: Path, out: Path) -> str:
    root, out = Path(root), Path(out)
    if not (root/'lineage.json').is_file():
        raise ValueError(f'{root} is not an atelier: no lineage.json')
    with tarfile.open(out, 'w:gz') as tar:
        for path, name in members(root):
            tar.add(path, arcname=name, recursive=False)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({'archive': str(out), 'sha256': digest, 'bytes': out.stat().st_size}))
    return digest


def fetch(source: str) -> bytes:
    if source.startswith(('https://', 'http://')):
        with urllib.request.urlopen(source, timeout=120) as response:
            return response.read()
    return Path(source).read_bytes()


def import_(source: str, sha256: str, into: Path) -> dict:
    into = Path(into)
    if (into/'lineage.json').exists():
        return {'imported': False, 'reason': 'the atelier already lives here; nothing is overwritten'}
    data = fetch(source)
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256.lower():
        raise ValueError(f'archive sha256 {digest} does not match {sha256}')
    into.mkdir(parents=True, exist_ok=True)
    staging = into.parent/(into.name + '.import')
    staging.mkdir(exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        names = tar.getnames()
        if 'lineage.json' not in names or any(n.split('/')[0] in ('keys',) for n in names):
            raise ValueError('not an atelier history archive')
        tar.extractall(staging, filter='data')
    # lineage.json last: its presence is what marks the atelier as living.
    for path in sorted(staging.iterdir(), key=lambda p: p.name == 'lineage.json'):
        path.rename(into/path.name)
    staging.rmdir()
    return {'imported': True, 'sha256': digest, 'entries': len(names)}


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='mnemo history')
    sub = ap.add_subparsers(dest='action', required=True)
    e = sub.add_parser('export')
    e.add_argument('--root', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    i = sub.add_parser('import')
    i.add_argument('--source', required=True, help='https URL or path of the archive')
    i.add_argument('--sha256', required=True)
    i.add_argument('--into', type=Path, required=True, help='the atelier directory on the volume')
    a = ap.parse_args(argv)
    if a.action == 'export':
        export(a.root, a.out)
    else:
        print(json.dumps(import_(a.source, a.sha256, a.into)))
