"""Package a state archive into work frames, or recover from surviving packages.

A package holds frame.bin and metadata.json for the work's carrier adapter;
creating packages does not by itself embed bytes into an artistic surface.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from . import catalogue, fountain, payload


def write_new(path, data):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
        out.write(data)


def package(archive, destination, key, capacity=1024, work_ids=None):
    envelope = payload.seal(archive, key.public_key(), context=fountain.DOMAIN)
    encoder = fountain.Encoder(envelope, capacity, key)
    if work_ids is None:
        work_ids = [f'work-{i:06d}' for i in range(fountain.recommended_count(len(envelope), capacity))]
    else:
        work_ids = list(work_ids)
    if len(work_ids) < fountain.recommended_count(len(envelope), capacity):
        raise ValueError('too few works for 30% loss with 32-equation rank margin')
    cat = catalogue.create(encoder, work_ids)
    destination.mkdir(parents=True, exist_ok=False)
    write_new(destination / 'catalogue.json', catalogue.canonical(cat))
    write_new(destination / 'envelope.bin', envelope)
    for i in range(len(work_ids)):
        work = destination / f'{i:06d}'
        work.mkdir()
        write_new(work / 'frame.bin', encoder.frame(i))
        write_new(work / 'metadata.json', catalogue.canonical(catalogue.metadata(cat, i)))
    return cat


def recover(works, key):
    frames = []
    expected = None
    for work in works:
        frame = (work / 'frame.bin').read_bytes()
        metadata = json.loads((work / 'metadata.json').read_text())
        body = catalogue.validate_work(frame, metadata, key)
        if expected is not None and body != expected:
            raise ValueError('inconsistent catalogues')
        expected = body
        frames.append(frame)
    return fountain.recover(frames, key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    pack = sub.add_parser('pack')
    pack.add_argument('archive', type=Path)
    pack.add_argument('--output', type=Path, required=True)
    pack.add_argument('--key', type=Path, required=True, help='Existing key, or new mode-0600 file')
    pack.add_argument('--capacity', type=int, default=1024, help='Bytes per carrier, including 88-byte header/MAC')
    pack.add_argument('--work-ids', type=Path, help='JSON array of actual work IDs; default: pending work slots')
    restore = sub.add_parser('recover')
    restore.add_argument('works', type=Path, nargs='+')
    restore.add_argument('--key', type=Path, required=True)
    restore.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('check-loss')
    check.add_argument('bundle', type=Path)
    check.add_argument('--archive', type=Path, required=True)
    check.add_argument('--key', type=Path, required=True)
    check.add_argument('--seed', type=int, default=20261103)
    args = parser.parse_args()
    if args.command == 'pack' and not args.key.exists():
        args.key.parent.mkdir(parents=True, exist_ok=True)
        write_new(args.key, X25519PrivateKey.generate().private_bytes_raw())
    key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
    if args.command == 'pack':
        cat = package(args.archive.read_bytes(), args.output, key, args.capacity,
                      json.loads(args.work_ids.read_text()) if args.work_ids else None)
        print(json.dumps({'snapshot': cat['body']['snapshot'], 'k': cat['body']['k'],
                          'frames': len(cat['body']['works']), 'frame_bytes': args.capacity,
                          'catalogue_bytes_per_work': len(catalogue.canonical(cat))}))
    elif args.command == 'recover':
        data = recover(args.works, key)
        write_new(args.output, data)
        print(json.dumps({'recovered_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}))
    else:
        works = sorted(p for p in args.bundle.iterdir() if p.is_dir())
        lost = math.ceil(len(works) * 0.30)
        survivors = random.Random(args.seed).sample(works, len(works) - lost)
        data = recover(survivors, key)
        if data != args.archive.read_bytes():
            raise RuntimeError('archive mismatch')
        print(json.dumps({'frames': len(works), 'dropped': lost, 'survived': len(survivors),
                          'identical': True, 'archive_bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest(), 'seed': args.seed}))


if __name__ == '__main__':
    main()
