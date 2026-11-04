"""Explicit, versioned MusicXML decoder registry; work data never imports code."""
import hashlib
import hmac
import json
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import DecodeError
from .codecs.v1 import surface, frames, fountain

FIELD = 'scheherazade.decoder'
LEGACY = ('romantic', 'nocturne', '1')
FOUNTAIN = ('romantic', 'nocturne-fountain', '1')


@dataclass
class Decoded:
    transport: str
    frame: object


def legacy(root, key):
    return Decoded('multipart-v1', frames.unpack(surface.decode(root), key, surface.context(root)))


def fountain_music(root, key):
    block = surface.decode(root)
    if len(block) < 36:
        raise DecodeError('truncated music frame')
    size = struct.unpack('>I', block[:4])[0]
    if not fountain.OVERHEAD < size <= len(block) - 36 or any(block[36+size:]):
        raise DecodeError('invalid music frame length/padding')
    frame, tag = block[4:4+size], block[4+size:36+size]
    expected = hmac.digest(fountain.mac_key(key), b'music-context-v1\0' +
                           surface.context(root) + block[:4+size], 'sha256')
    if not hmac.compare_digest(tag, expected):
        raise DecodeError('music context authentication failed')
    fountain.unpack(frame, key)
    return Decoded('fountain-v1', frame)


DECODERS = {LEGACY: legacy, FOUNTAIN: fountain_music}

# Explicit identities: loading a work never imports its named composer.
SCHOOL_NAMES = ('additive', 'aleatoric_counterpoint', 'chance', 'drone',
                'feldman', 'fibonacci', 'in_c', 'messiaen', 'micropolyphony',
                'polystylism', 'process', 'scelsi', 'serial', 'sonorism',
                'spectral', 'stochastic', 'tempo_canon', 'tintinnabuli', 'ustvolskaya')


def school_fountain(root, key):
    from .codecs.v1 import schools
    return Decoded('fountain-v1', schools.read_fountain(root, key))


def school_multipart(root, key):
    from .codecs.v1 import schools
    return Decoded('multipart-v1', schools.read_frame(root, key))


def school_series(root, key):
    from .codecs.v2.schools import decode_many
    return Decoded('fountain-batch-v1', decode_many(root, key))


for school in SCHOOL_NAMES:
    DECODERS[(school, 'dynamics-fountain', '1')] = school_fountain
    DECODERS[(school, 'dynamics-multipart', '1')] = school_multipart
    DECODERS[(school, 'dynamics-fountain', '2')] = school_series


def descriptor(root):
    fields = root.findall(f'./identification/miscellaneous/miscellaneous-field[@name="{FIELD}"]')
    if not fields:
        # Original nocturne v1 predates the marker; its MAC must still verify.
        return LEGACY
    if len(fields) != 1:
        raise DecodeError('duplicate decoder descriptor')
    try:
        data = json.loads(fields[0].text)
        identity = tuple(data[k] for k in ('school', 'method', 'version'))
        if not all(isinstance(v, str) for v in identity):
            raise ValueError('descriptor values must be strings')
        return identity
    except (ValueError, KeyError, TypeError) as exc:
        raise DecodeError('invalid decoder descriptor') from exc


def decode(path, key):
    root = surface.read(path)
    if not root.findall(f'./identification/miscellaneous/miscellaneous-field[@name="{FIELD}"]'):
        from .codecs.v1 import schools
        if any(d.get('id', '').startswith(schools.PREFIX) for d in root.iter('direction')):
            # Task-17 works predate registry markers. Both attempts still
            # authenticate the full XML context with their original wire MAC.
            try:
                return school_fountain(root, key)
            except DecodeError:
                return school_multipart(root, key)
    identity = descriptor(root)
    decoder = DECODERS.get(identity)
    if decoder is None:
        raise DecodeError(f'unsupported decoder: {identity}')
    return decoder(root, key)


def mark(root, identity):
    if identity not in DECODERS:
        raise ValueError('unregistered decoder')
    if root.findall(f'.//miscellaneous-field[@name="{FIELD}"]'):
        raise ValueError('work already has a decoder descriptor')
    identification = root.find('identification')
    if identification is None:
        identification = ET.Element('identification')
        root.insert(0, identification)
    misc = identification.find('miscellaneous')
    if misc is None:
        misc = ET.SubElement(identification, 'miscellaneous')
    ET.SubElement(misc, 'miscellaneous-field', name=FIELD).text = json.dumps(
        dict(zip(('school', 'method', 'version'), identity)), sort_keys=True)
    return root


def encode_fountain(source, destination, frame, key):
    """Existing approved surface only; insufficient capacity is an error."""
    fountain.unpack(frame, key)
    root = mark(surface.read(source), FOUNTAIN)
    body = struct.pack('>I', len(frame)) + frame
    block = body + hmac.digest(fountain.mac_key(key), b'music-context-v1\0' +
                               surface.context(root) + body, 'sha256')
    capacity = surface.capacity(root)
    if len(block) > capacity:
        raise ValueError(f'frame needs {len(block)} bytes; surface holds {capacity}')
    encoded = surface.encode(root, block.ljust(capacity, b'\0'))
    # Validate before publishing, and never overwrite a work.
    if fountain_music(encoded, key).frame != frame:
        raise DecodeError('carrier round trip failed')
    with destination.open('xb') as out:
        ET.ElementTree(encoded).write(out, encoding='utf-8', xml_declaration=True)
