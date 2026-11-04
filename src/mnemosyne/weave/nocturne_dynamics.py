"""Approved nocturne performance channel, using the retained v2 alphabet.

Follow the written dynamics and hairpins, never infer phrases from cluster data.
Hairpins without a target dynamic move one conventional dynamic step (12 points).
All original XML elements survive unchanged; only silent-print sound knots are added.
"""
from copy import deepcopy
from fractions import Fraction
import xml.etree.ElementTree as ET

from . import schools

IDENTITY = ('romantic', 'nocturne-dynamics-fountain', '2')
LEVELS = {'ppp': 15, 'pp': 25, 'p': 35, 'mp': 45, 'mf': 57, 'f': 69, 'ff': 85, 'fff': 95}


def timeline(part):
    start = Fraction(0)
    divisions = 1
    for measure in part.findall('measure'):
        divisions = int(measure.findtext('attributes/divisions', str(divisions)))
        cursor = extent = Fraction(0)
        for el in list(measure):
            at = start + cursor + Fraction(el.findtext('offset', '0')) / divisions
            yield measure, el, at, divisions
            if el.tag in ('backup', 'forward'):
                cursor += Fraction(int(el.findtext('duration', '0')), divisions) * (-1 if el.tag == 'backup' else 1)
            elif el.tag == 'note' and el.find('chord') is None and el.find('grace') is None:
                cursor += Fraction(int(el.findtext('duration', '0')), divisions)
            extent = max(extent, cursor)
        start += extent


def prepare(root):
    root = deepcopy(root)
    if schools.slots(root):
        raise ValueError('surface already prepared')
    ordinal = 0
    for part in root.findall('part'):
        events = list(timeline(part))
        dynamics = [(Fraction(0), 45.0)]
        hairpins, opened = [], {}
        for _, el, at, _ in events:
            if el.tag != 'direction':
                continue
            dyn = el.find('direction-type/dynamics')
            sound = el.find('sound')
            if dyn is not None and len(dyn):
                value = LEVELS[dyn[0].tag]
                if sound is not None and 'dynamics' in sound.attrib:
                    value = float(sound.get('dynamics'))
                dynamics.append((at, value))
            wedge = el.find('direction-type/wedge')
            if wedge is not None:
                number = wedge.get('number', '1')
                kind = wedge.get('type')
                if kind in ('crescendo', 'diminuendo'):
                    opened[number] = (at, kind)
                elif kind == 'stop' and number in opened:
                    begin, kind = opened.pop(number)
                    if at > begin:
                        hairpins.append((begin, at, kind))
        dynamics.sort(key=lambda item: item[0])

        segments = []
        for begin, end, kind in sorted(hairpins):
            initial = next(v for t, v in reversed(dynamics) if t <= begin)
            target = next((v for t, v in dynamics if t == end), initial + (12 if kind == 'crescendo' else -12))
            target = max(4, min(98, target))
            segments.append((begin, end, initial, target))
            if not any(t == end for t, _ in dynamics):
                dynamics.append((end, target))
                dynamics.sort(key=lambda item: item[0])

        def base(at):
            value = next(v for t, v in reversed(dynamics) if t <= at)
            for begin, end, initial, target in segments:
                if begin <= at <= end:
                    value = initial + (target-initial)*float((at-begin)/(end-begin))
            return round(max(4, min(98, value)), 6)

        for measure, el, at, divisions in events:
            if (el.tag != 'note' or any(el.find(tag) is not None for tag in ('rest', 'chord', 'grace'))):
                continue
            duration = Fraction(int(el.findtext('duration', '0')), divisions)
            offset = Fraction(0)
            while offset < duration:
                ticks = offset * divisions
                if ticks.denominator != 1:
                    raise ValueError('divisions cannot express half-quarter knots')
                value = base(at + offset)
                d = ET.Element('direction', id=f'{schools.PREFIX}{ordinal}-{value:g}', **{'print-object': 'no'})
                ordinal += 1
                dtype = ET.SubElement(d, 'direction-type')
                ET.SubElement(dtype, 'words').text = ''
                ET.SubElement(d, 'offset', sound='yes').text = str(int(ticks))
                if el.find('staff') is not None:
                    ET.SubElement(d, 'staff').text = el.findtext('staff')
                ET.SubElement(d, 'sound', dynamics=f'{value:g}')
                measure.insert(list(measure).index(el), d)
                offset += Fraction(1, 2)
    return root
