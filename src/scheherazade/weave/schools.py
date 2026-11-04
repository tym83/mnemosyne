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


def prepare(root, school):
    """Add bounded expressive dynamics knots without altering note grammar."""
    from scheherazade.music.schools import SCHOOLS
    rules = SCHOOLS[school].FREE_CHANNELS
    if (rules['levels'],rules['step_percent'],rules['max_deviation_percent']) != (16,.25,1.875):
        raise ValueError('school rules require a different surface codec version')
    root = deepcopy(root)
    if any(d.get('id', '').startswith(PREFIX) for d in root.iter('direction')):
        raise ValueError('surface already prepared')
    ordinal = 0
    for part in root.findall('part'):
        divisions = 1
        baseline = 63.0
        symbol = 'mp'
        for measure in part.findall('measure'):
            divisions = int(measure.findtext('attributes/divisions', str(divisions)))
            for element in list(measure):
                if element.tag == 'direction':
                    dyn = element.find('direction-type/dynamics')
                    sound = element.find('sound')
                    if dyn is not None and len(dyn):
                        symbol = dyn[0].tag
                    if sound is not None and 'dynamics' in sound.attrib:
                        baseline = float(sound.get('dynamics'))
                if (element.tag != 'note' or element.find('rest') is not None
                        or element.find('chord') is not None or element.find('grace') is not None):
                    continue
                duration = int(element.findtext('duration', '0'))
                step = Fraction(str(rules['period_quarters'])) * divisions
                offset = Fraction(0)
                while offset < duration:
                    # Fractional MusicXML offsets would lose precision in some readers.
                    if offset.denominator != 1:
                        raise ValueError('divisions cannot express surface grid')
                    direction = ET.Element('direction', {'id': f'{PREFIX}{ordinal}-{baseline:g}', 'placement': 'below'})
                    ordinal += 1
                    dtype = ET.SubElement(direction, 'direction-type')
                    dynamic = ET.SubElement(dtype, 'dynamics')
                    ET.SubElement(dynamic, symbol)
                    ET.SubElement(direction, 'offset', {'sound': 'yes'}).text = str(int(offset))
                    # Each knot is a performance variant within the same written level.
                    ET.SubElement(direction, 'sound', {'dynamics': f'{baseline:g}'})
                    measure.insert(list(measure).index(element), direction)
                    offset += step
    return root


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


def expression_curves(root):
    """Actual performance gain knots, one curve per part, in quarter-note time.

    music21 imports the symbolic dynamic but ignores MusicXML sound/dynamics.
    Keep this explicit adapter for continuous sound, including sustained notes.
    It does not extract payload; sound carries the same choices used by decode.
    """
    curves = []
    for part in root.findall('part'):
        curve = []
        measure_start = Fraction(0)
        divisions = 1
        for measure in part.findall('measure'):
            divisions = int(measure.findtext('attributes/divisions',str(divisions)))
            cursor = Fraction(0)
            extent = Fraction(0)
            for el in measure:
                if el.tag == 'direction' and el.get('id','').startswith(PREFIX):
                    base = float(el.get('id').rsplit('-',1)[-1])
                    at = measure_start+cursor+Fraction(el.findtext('offset','0'))/divisions
                    value = float(el.find('sound').get('dynamics'))
                    curve.append((float(at),value/base))
                elif el.tag in ('backup','forward'):
                    cursor += Fraction(int(el.findtext('duration','0')),divisions)*(-1 if el.tag=='backup' else 1)
                    extent = max(extent,cursor)
                elif el.tag=='note' and el.find('chord') is None and el.find('grace') is None:
                    cursor += Fraction(int(el.findtext('duration','0')),divisions)
                    extent = max(extent,cursor)
            measure_start += extent
        curves.append(sorted(curve))
    return curves


def performance_score(path):
    """Import MusicXML with the continuous dynamics adapter for atelier rendering."""
    from music21 import converter
    root = surface.read(path)
    digits(root)  # reject invalid, nonnumeric/out-of-alphabet automation
    score = converter.parse(path).toSoundingPitch()
    for part,curve in zip(score.parts,expression_curves(root),strict=True):
        part.editorial.school_expression = curve
    return score
