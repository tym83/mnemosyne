"""Cluster state over time: keyframes and deltas, carried by works across nights.

The payload is the cluster only. The atelier's own history (artists, works,
notebooks, biographies, reviews) is never payload: it is the fabric that
carries it. Each night the observed state becomes a piece, either a keyframe
(the whole state) or a delta (changed and removed objects since the previous
piece). A piece is sealed once and fountain-coded; its frames are rateless, so
works of later nights continue the same piece until it has enough frames to
survive the loss of 30% of them. Restore chooses a moment and replays the
chain from its keyframe.

Volume data is not here: only API objects. Data backups (Velero, database
operators, disk snapshots) are API objects themselves and can be listed in the
snapshot inventory as the map to the data.
"""
from __future__ import annotations

import hashlib
import io
import math
import json
from pathlib import Path
import tarfile

import yaml
import zstandard

from .collect import normalize

MAGIC = b'MNEMOSYNE-PIECE-1\n'
FRAME_BYTES = 256
KEYFRAME_EVERY = 30
LOSS = .30
# Extra independent equations among survivors: rank failure below 2**-MARGIN.
MARGIN = 16


def identity(obj):
    return [obj['apiVersion'], obj['kind'], obj['metadata'].get('namespace', ''), obj['metadata']['name']]


def member_name(ident):
    return hashlib.sha256(json.dumps(list(ident), separators=(',', ':')).encode()).hexdigest() + '.yaml'


def members(objects, *, include_secrets=False):
    from ..atelier import is_atelier_object
    result = {}
    for source in objects:
        if is_atelier_object(source):
            continue  # the atelier is the carrier, never the payload
        obj = normalize(source, include_secrets=include_secrets)
        if obj is None:
            continue
        name = member_name(identity(obj))
        if name in result:
            raise ValueError(f'duplicate object: {identity(obj)}')
        result[name] = yaml.safe_dump(obj, sort_keys=True, allow_unicode=True).encode()
    return result


def pack(selected: dict) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(selected.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
    return zstandard.ZstdCompressor(level=9, write_checksum=True).compress(stream.getvalue())


def digests(selected: dict) -> dict:
    return {name: hashlib.sha256(data).hexdigest() for name, data in selected.items()}


def state_id(hashes: dict) -> str:
    return hashlib.sha256(json.dumps(sorted(hashes.items()), separators=(',', ':')).encode()).hexdigest()


def piece(header: dict, archive: bytes | None) -> bytes:
    return MAGIC + json.dumps(header, sort_keys=True, separators=(',', ':')).encode() + b'\n' + (archive or b'')


def parse(data: bytes):
    """(header, archive) for a piece, (None, data) for a legacy single archive."""
    if not data.startswith(MAGIC):
        return None, data
    line, _, archive = data[len(MAGIC):].partition(b'\n')
    header = json.loads(line)
    if header.get('kind') not in ('keyframe', 'delta') or not isinstance(header.get('removed', []), list):
        raise ValueError('invalid state piece')
    return header, archive or None


class Ledger:
    """Atelier-private bookkeeping beside the checkpoint; envelopes are encrypted."""
    def __init__(self, root: Path):
        self.root = Path(root)
        path = self.root/'ledger.json'
        data = json.loads(path.read_text()) if path.exists() else {}
        self.state = data.get('state', {})
        self.state_id = data.get('state_id')
        self.deltas = data.get('deltas', 0)
        self.pieces = data.get('pieces', [])

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root/'ledger.json').write_text(json.dumps(
            {'state': self.state, 'state_id': self.state_id, 'deltas': self.deltas, 'pieces': self.pieces}, indent=1))

    def envelope(self, entry) -> bytes:
        return (self.root/'envelopes'/f'{entry["id"]}.bin').read_bytes()

    def observe(self, objects, at: str, recipient, *, include_secrets=False) -> dict | None:
        """Turn tonight's cluster state into a sealed piece; None when nothing changed."""
        from ..weave import fountain, payload
        current = members(objects, include_secrets=include_secrets)
        hashes = digests(current)
        sid = state_id(hashes)
        if sid == self.state_id:
            return None
        changed = {n: d for n, d in current.items() if self.state.get(n) != hashes[n]}
        removed = sorted(n for n in self.state if n not in current)
        whole = pack(current)
        delta = pack(changed) if changed else None
        keyframe = (self.state_id is None or self.deltas >= KEYFRAME_EVERY
                    or len(delta or b'') + 64 * len(removed) > len(whole) // 2)
        header = {'kind': 'keyframe' if keyframe else 'delta', 'at': at, 'state': sid,
                  'parent': None if keyframe else self.state_id, 'removed': [] if keyframe else removed,
                  'objects': len(current)}
        data = piece(header, whole if keyframe else delta)
        envelope = payload.seal(data, recipient, context=fountain.DOMAIN)
        k, _ = fountain.dimensions(len(envelope), FRAME_BYTES)
        entry = {'id': sid, 'kind': header['kind'], 'at': at, 'parent': header['parent'],
                 'bytes': len(data), 'envelope_bytes': len(envelope), 'frame_bytes': FRAME_BYTES,
                 'k': k, 'target': math.ceil((k + MARGIN) / (1 - LOSS)),
                 'next': 0, 'carried': 0, 'complete': False}
        (self.root/'envelopes').mkdir(parents=True, exist_ok=True)
        (self.root/'envelopes'/f'{sid}.bin').write_bytes(envelope)
        self.pieces.append(entry)
        self.state, self.state_id = hashes, sid
        self.deltas = 0 if keyframe else self.deltas + 1
        return entry

    def pending(self):
        return [p for p in self.pieces if not p['complete']]

    def assign(self, capacities: list[int]) -> list[tuple[dict, int, int] | None]:
        """For each carrier capacity: (piece, first frame index, count) or None.

        Oldest pieces first, a whole carrier per piece: a work carries one snapshot.
        Assignments are reserved immediately; call commit() after the works are written.
        """
        plan, reserved = [], {}
        for capacity in capacities:
            choice = None
            for entry in self.pending():
                room = entry['target'] - entry['carried'] - reserved.get(entry['id'], 0)
                fits = capacity // entry['frame_bytes']
                if room > 0 and fits > 0:
                    count = min(room, fits)
                    choice = (entry, entry['next'] + reserved.get(entry['id'], 0), count)
                    reserved[entry['id']] = reserved.get(entry['id'], 0) + count
                    break
            plan.append(choice)
        return plan

    def commit(self, plan):
        for choice in plan:
            if choice is None:
                continue
            entry, _, count = choice
            entry['next'] += count
            entry['carried'] += count
            entry['complete'] = entry['carried'] >= entry['target']


def replay(pieces: list[tuple[dict, bytes | None]], at: str | None = None):
    """State at a moment from recovered pieces: newest restorable state not after `at`."""
    from ..restore import read_archive
    by_id = {h['state']: (h, a) for h, a in pieces}
    candidates = sorted((h for h, _ in pieces if at is None or h['at'] <= at), key=lambda h: h['at'], reverse=True)
    for head in candidates:
        chain, cursor, ok = [], head, True
        while cursor['kind'] == 'delta':
            chain.append(cursor)
            if cursor['parent'] not in by_id:
                ok = False
                break
            cursor = by_id[cursor['parent']][0]
        if not ok:
            continue
        chain.append(cursor)
        state: dict[str, bytes] = {}
        for h in reversed(chain):
            archive = by_id[h['state']][1]
            if h['kind'] == 'keyframe':
                state = {}
            for name in h['removed']:
                state.pop(name, None)
            if archive:
                state.update(_members(archive))
        if state_id(digests(state)) != head['state']:
            raise ValueError(f'replayed state does not match {head["state"]}')
        data = pack(state)
        return data, read_archive(data), {'moment': head['at'], 'state': head['state'],
                                          'chain': [h['state'] for h in reversed(chain)]}
    raise ValueError('no complete chain from a keyframe to the requested moment')


def _members(archive: bytes) -> dict[str, bytes]:
    from ..restore import MAX_ARCHIVE
    raw = zstandard.ZstdDecompressor().decompress(archive, max_output_size=MAX_ARCHIVE)
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as tar:
        for member in tar:
            if not member.isfile():
                raise ValueError('nonregular member in piece')
            result[member.name] = tar.extractfile(member).read()
    return result
