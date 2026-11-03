"""Encode one whole frame, or decode MusicXML files with only a private key."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import converter
from scheherazade.architecture import state_at
from . import DecodeError, frames, payload, surface
from .music import canonical, style_check


def decode(xml, key):
    try:
        root = surface.read(xml)
        return frames.unpack(surface.decode(root), key, surface.context(root))
    except DecodeError:
        raise
    except (ValueError, IndexError, TypeError, KeyError, AttributeError) as exc:
        raise DecodeError('invalid music channel') from exc


def encode(xml, destination, envelope, index, key):
    root = surface.read(xml)
    block = frames.pack(envelope, index, surface.capacity(root), key, surface.context(root))
    encoded = surface.encode(root, block)
    if surface.context(encoded) != surface.context(root):
        raise RuntimeError('protected musical context changed')
    surface.write(encoded, destination)
    recovered = decode(destination, key)
    if recovered['data'] != envelope[index*recovered['chunk_size']:index*recovered['chunk_size']+len(recovered['data'])]:
        raise RuntimeError('MusicXML-only round trip failed')
    return recovered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xml', type=Path, default=Path('out/works/music/nocturne/p02_000.xml'))
    parser.add_argument('--output', type=Path, default=Path('out/works/music/nocturne/p02_000.backup.musicxml'))
    parser.add_argument('--key', type=Path, default=Path('out/codex/nocturne-backup.key'))
    parser.add_argument('--envelope', type=Path, default=Path('out/codex/nocturne-backup.envelope'))
    parser.add_argument('--index', type=int, default=0)
    parser.add_argument('--decode', nargs='+', type=Path)
    parser.add_argument('--recovered', type=Path)
    args = parser.parse_args()
    if args.decode:
        key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
        fs = [decode(p, key) for p in args.decode]
        if args.recovered:
            data = frames.assemble(fs, key)
            args.recovered.write_bytes(data)
        print(json.dumps([{'index': f['index'], 'count': f['count'], 'bytes': len(f['data'])} for f in fs]))
        return
    args.key.parent.mkdir(parents=True, exist_ok=True)
    if not args.key.exists():
        with os.fdopen(os.open(args.key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
            f.write(X25519PrivateKey.generate().private_bytes_raw())
    key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
    state = state_at(Path('out/scenarios/shop/ops.jsonl'), datetime.fromisoformat('2025-07-01T00:00:00+00:00'))
    objects = [v for (kind, _, _), v in sorted(state.items()) if kind != 'Secret']
    data = canonical(next(v for v in objects if v['kind'] == 'Namespace' and v['metadata']['name'] == 'shop'))
    if not args.envelope.exists():
        args.envelope.write_bytes(payload.seal(data, key.public_key(), context=frames.DOMAIN))
    envelope = args.envelope.read_bytes()
    if payload.open_envelope(envelope, key, context=frames.DOMAIN) != data:
        raise RuntimeError('saved envelope differs from current state')
    frame = encode(args.xml, args.output, envelope, args.index, key)
    original, encoded = [converter.parse(str(p)) for p in (args.xml, args.output)]
    bars = len(original.parts[0].getElementsByClass('Measure'))
    expanded = encoded.expandRepeats()
    seconds = sum(float(b-a)*60/m.getQuarterBPM() for a,b,m in expanded.metronomeMarkBoundaries())
    root = surface.read(args.output)
    failures = {}
    for label, target in [('melody', './part/measure/note[staff="1"]/pitch/octave'),
                          ('accompaniment', './part/measure/note[staff="2"]/pitch/octave')]:
        changed = deepcopy(root)
        n = changed.find(target)
        n.text = str(int(n.text)+1)
        path = args.output.with_name(args.output.stem + '.tampered-' + label + '.musicxml')
        surface.write(changed, path)
        try:
            decode(path, key)
        except DecodeError as exc:
            failures[label] = str(exc)
        else:
            raise RuntimeError('tampering accepted')
    report = dict(status='verified_partial_encrypted_frame', channel_bytes=surface.capacity(root),
        carried_envelope_bytes=len(frame['data']), envelope_bytes=len(envelope),
        remaining_envelope_bytes=len(envelope)-len(frame['data']), frame_index=frame['index'],
        frame_count=frame['count'], frame_round_trip=True, full_payload_recovered=False,
        fragment_plaintext_bytes=len(data), fragment_sha256=hashlib.sha256(data).hexdigest(),
        fragment_percent_of_state=100*len(data)/len(canonical(objects)), restored_state_bytes=0,
        bars=bars, playback_seconds=seconds, frame_bits_per_bar=8*surface.capacity(root)/bars,
        envelope_bits_per_bar=8*len(frame['data'])/bars,
        frame_bits_per_minute=8*surface.capacity(root)*60/seconds,
        envelope_bits_per_minute=8*len(frame['data'])*60/seconds,
        original_style=style_check(original), encoded_style=style_check(encoded), tamper_checks=failures)
    args.output.with_suffix('.measurements.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
