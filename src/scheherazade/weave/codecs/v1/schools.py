"""School performance-dynamics channel v1; payload lives in MusicXML sound.

Grammar choices are intentionally separate: discarded RNG draws are not carriers.
The exact arithmetic source drives only the declared, observable free choices.
Every knot is on a sounding span; no rests or metadata carry payload bits.
The XML context (including notes, rules, knot positions and baseline) is MACed.
"""
from copy import deepcopy
from fractions import Fraction
import hmac
import json
import random
import xml.etree.ElementTree as ET

from . import DecodeError, arithmetic, frames, fountain, payload, surface

PREFIX = 'school-dynamics-v1-'
DOMAIN = b'scheherazade/school-dynamics/v1'


class ArithmeticChoices:
    """Exact finite equiprobable choice source, exhausted once per surface."""
    def __init__(self, block, radices):
        self.digits = iter(arithmetic.encode(block, radices))

    def choice(self, options):
        return options[next(self.digits)]


def slots(root):
    result = []
    for d in root.iter('direction'):
        marker = d.get('id', '')
        if marker.startswith(PREFIX):
            try:
                base = float(marker.rsplit('-', 1)[-1])
                sound = d.find('sound')
                if sound is None or sound.get('dynamics') is None:
                    raise ValueError('missing sound dynamics')
                opts = [round(base + (i-7.5)*.25, 6) for i in range(16)]
                if min(opts) <= 0:
                    raise ValueError('invalid baseline')
                result.append((sound, opts))
            except (ValueError, TypeError) as exc:
                raise DecodeError('invalid dynamics carrier') from exc
    return result


def capacity(root):
    return arithmetic.capacity([16]*len(slots(root)))


def context(root):
    root = deepcopy(root)
    for sound, opts in slots(root):
        sound.set('dynamics', str(opts[0]))
    def tree(e):
        return [e.tag, sorted(e.attrib.items()), (e.text or '').strip(), [tree(c) for c in e]]
    return DOMAIN + json.dumps(tree(root), separators=(',', ':')).encode()


def encode(root, block):
    root = deepcopy(root)
    ss = slots(root)
    if len(block) != capacity(root):
        raise ValueError('block must fill capacity')
    source = ArithmeticChoices(block, [16]*len(ss))
    for sound, opts in ss:
        sound.set('dynamics', str(source.choice(opts)))
    return root


def unwoven(root, seed):
    root = deepcopy(root)
    rng = random.Random(seed)
    for sound, opts in slots(root):
        sound.set('dynamics', str(rng.choice(opts)))
    return root


def digits(root):
    try:
        return [opts.index(float(sound.get('dynamics'))) for sound, opts in slots(root)]
    except (ValueError, TypeError, AttributeError) as exc:
        raise DecodeError('dynamics outside school alphabet') from exc


def decode(root):
    return arithmetic.decode(digits(root), [16]*len(slots(root)), capacity(root))


def weave_frame(root, envelope, index, key):
    return encode(root, frames.pack(envelope, index, capacity(root), key, context(root)))


def read_frame(root, key):
    return frames.unpack(decode(root), key, context(root))


def weave_fountain(root, encoder, index, key):
    """Task-08 frame plus work MAC; fountain MAC alone does not bind music."""
    frame = encoder.frame(index)
    body_size = capacity(root)-12
    if len(frame) != body_size:
        raise ValueError('fountain encoder capacity must equal surface capacity minus 12')
    tag = hmac.digest(frames.mac_key(key), context(root)+frame, 'sha256')[:12]
    return encode(root, frame+tag)


def read_fountain(root, key):
    block = decode(root)
    frame, tag = block[:-12], block[-12:]
    if not hmac.compare_digest(tag, hmac.digest(frames.mac_key(key), context(root)+frame, 'sha256')[:12]):
        raise DecodeError('work/fountain authentication failed')
    fountain.unpack(frame, key)
    return frame

