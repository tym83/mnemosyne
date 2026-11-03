"""Version 1 conservative Romantic surface, decoded from sounding XML notes.

Keeps the bass and spelled pitch classes of every chord. Uses only
2--5 note voicings within a tenth and quarter/two-eighth repeated chords.
No ornaments, ties, slurs, tuplets or polyphonic LH measures are rewritten.
"""
from copy import deepcopy
from itertools import combinations
import json
import xml.etree.ElementTree as ET

from . import DecodeError, arithmetic


def pitch(n):
    p = n.find('pitch')
    return (p.findtext('step'), int(p.findtext('alter', '0')), int(p.findtext('octave')))


def midi(p):
    return 12 * (p[2] + 1) + {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[p[0]] + p[1]


def voicings(ps, ceiling=108):
    ps = sorted(ps, key=midi)
    lo = ps[0]
    if not 21 <= midi(lo) <= 108:
        return []
    pcs = {p[:2] for p in ps}
    inside = sorted([(s, a, o) for s, a in pcs for o in range(9)
                     if midi(lo) < midi((s, a, o)) <= min(ceiling, midi(lo)+16, 108)], key=midi)
    return sorted({tuple(sorted((lo, *middle), key=midi))
                   for size in range(1, 5) for middle in combinations(inside, size)
                   if {p[:2] for p in (lo, *middle)} == pcs})


def notes(ps, duration, divisions, voice):
    result = []
    for i, (s, a, o) in enumerate(ps):
        n = ET.Element('note')
        if i:
            ET.SubElement(n, 'chord')
        p = ET.SubElement(n, 'pitch')
        ET.SubElement(p, 'step').text = s
        if a:
            ET.SubElement(p, 'alter').text = str(a)
        ET.SubElement(p, 'octave').text = str(o)
        ET.SubElement(n, 'duration').text = str(duration)
        ET.SubElement(n, 'voice').text = voice
        ET.SubElement(n, 'type').text = 'quarter' if duration == divisions else 'eighth'
        ET.SubElement(n, 'staff').text = '2'
        result.append(n)
    return result


def slots(root):
    """Find quarter cells; identical eighth pairs are the same cell on decode."""
    result = []
    for part in root.findall('part'):
        divisions = None
        for measure in part.findall('measure'):
            d = measure.findtext('attributes/divisions')
            if d:
                divisions = int(d)
            if not divisions or divisions % 2:
                continue
            upper = [midi(pitch(n)) for n in measure.findall("note")
                     if n.findtext("staff") == "1" and n.find("pitch") is not None]
            ceiling = min(upper, default=108)
            lh = [n for n in measure.findall('note') if n.findtext('staff') == '2']
            if len({n.findtext('voice') for n in lh}) != 1:
                continue
            groups = []
            cursor = 0
            for n in lh:
                if n.find('chord') is None:
                    groups.append((cursor, []))
                    cursor += int(n.findtext('duration', '0'))
                groups[-1][1].append(n)
            i = 0
            while i < len(groups):
                start, group = groups[i]
                duration = int(group[0].findtext('duration', '0'))
                cell = group
                split = False
                if duration * 2 == divisions and i+1 < len(groups):
                    nxt = groups[i+1][1]
                    if all(n.find('pitch') is not None for n in group+nxt) and (
                        [pitch(n) for n in group] == [pitch(n) for n in nxt]
                        and int(nxt[0].findtext('duration', '0')) == duration):
                        cell = group+nxt
                        split = True
                allowed = {'chord', 'pitch', 'duration', 'voice', 'type', 'staff', 'accidental', 'beam', 'stem'}
                if (start % divisions == 0 and (duration == divisions or split)
                        and len(group) >= 2 and all(n.find('pitch') is not None
                        and all(c.tag in allowed for c in n) for n in cell)):
                    ps = tuple(sorted((pitch(n) for n in group), key=midi))
                    opts = voicings(ps, ceiling)
                    if ps in opts:
                        result.append((measure, cell, opts, opts.index(ps)*2+int(split), divisions))
                        i += int(split)
                i += 1
    return result


def replace(measure, old, new):
    index = list(measure).index(old[0])
    for n in old:
        measure.remove(n)
    for n in reversed(new):
        measure.insert(index, n)


def context(root):
    """Canonical XML tree with every carrier cell reset, no hidden side channel.

    Layout and metadata are authenticated too; pretty-print whitespace is not.
    This deliberately does not promise survival through arbitrary XML editors.
    """
    root = deepcopy(root)
    for m, ns, opts, _, div in slots(root):
        replace(m, ns, notes(opts[0], div, div, ns[0].findtext('voice')))
    def tree(e):
        return [e.tag, sorted(e.attrib.items()), (e.text or '').strip(), [tree(c) for c in e]]
    return json.dumps(tree(root), separators=(',', ':')).encode()


def capacity(root):
    return arithmetic.capacity([2*len(s[2]) for s in slots(root)])


def encode(root, block):
    root = deepcopy(root)
    ss = slots(root)
    size = capacity(root)
    if len(block) != size:
        raise ValueError('block must fill channel capacity')
    digits = arithmetic.encode(block, [2*len(s[2]) for s in ss])
    for (m, ns, opts, _, div), digit in zip(ss, digits):
        ps, split = opts[digit//2], digit%2
        new = notes(ps, div//2 if split else div, div, ns[0].findtext('voice'))
        if split:
            new += deepcopy(new)
        replace(m, ns, new)
    return root


def decode(root):
    ss = slots(root)
    return arithmetic.decode([s[3] for s in ss], [2*len(s[2]) for s in ss], capacity(root))


def read(path):
    try:
        return ET.parse(path).getroot()
    except (ET.ParseError, ValueError) as exc:
        raise DecodeError('invalid MusicXML') from exc


def write(root, path):
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
