"""Deterministic performance practice; MusicXML directions and MIDI share a timeline.

Harp pedals change pitch, not damping: harp resonance is release/l.v., never CC64.
No resonance decisions carry backup bits.
"""
import xml.etree.ElementTree as ET
from .instrumentarium import REGISTRY, release_profile


def apply(score, plan):
    school = plan.get('school')
    total = float(plan['duration']) * plan['tempo'] / 60 if 'duration' in plan else float(score.highestTime)
    # Current tintinnabuli grammar uses a single tonic triad throughout. Form
    # sections change texture, not harmony. Explicit harmony spans can refine it.
    spans = plan.get('pedal_harmonies', [[0, total]])
    if school == 'tintinnabuli':
        previous = 0.
        for a,b in spans:
            if not previous <= a < b <= total:
                raise ValueError('Pedal harmonies must be ordered and non-overlapping')
            previous = b
    for part in score.parts:
        # Imported music21 pedal spanners cannot faithfully re-export terminal
        # anchors. Replace them with this exact deterministic direction timeline.
        for mark in list(part.recurse().getElementsByClass('PedalMark')):
            mark.activeSite.remove(mark)
        ins = part.recurse().getElementsByClass('Instrument').first()
        names = [n for n, spec in REGISTRY.items() if spec.get('gm_program') == ins.midiProgram and not spec.get('unpitched')]
        profile = release_profile(names[0]) if names else {}
        pedal = []
        if profile.get('pedal') and school in ('tintinnabuli', 'feldman'):
            for a, b in (spans if school == 'tintinnabuli' else [[0, total]]):
                if not 0 <= a < b <= total:
                    raise ValueError('Invalid pedal harmony interval')
                pedal.extend([(float(a), 127), (float(b), 0)])
        if profile.get('laissez_vibrer') and school in ('tintinnabuli','feldman','drone','spectral'):
            from music21 import expressions
            if not any(t.content == 'l.v.' for t in part.recurse().getElementsByClass(expressions.TextExpression)):
                part.insert(0, expressions.TextExpression('l.v.'))
        part.editorial.sustain_pedal = sorted(pedal, key=lambda e: (e[0], e[1]))
    return score


def pedal_events(part):
    return getattr(part.editorial, 'sustain_pedal', [])


def annotate_xml(path, score):
    """Insert standard pedal directions at exact offsets, including final release.

    music21's PedalMark export currently loses terminal SpannerAnchor releases;
    writing directions explicitly avoids that loss in both XML and musicxml2ly.
    """
    tree = ET.parse(path)
    for xml_part, part in zip(tree.findall('part'), score.parts, strict=True):
        measures = xml_part.findall('measure')
        starts = []
        at = 0.; divisions = 1
        for measure in measures:
            divisions = int(measure.findtext('attributes/divisions', divisions))
            cursor = end = 0
            for child in measure:
                dur = int(child.findtext('duration', '0'))
                if child.tag == 'backup': cursor -= dur
                elif child.tag == 'forward': cursor += dur
                elif child.tag == 'note' and child.find('chord') is None: cursor += dur
                end = max(end, cursor)
            starts.append((at, divisions, measure))
            at += end / divisions
        for offset, value in pedal_events(part):
            start, divisions, measure = next(x for x in reversed(starts) if x[0] <= offset + 1e-8)
            direction = ET.Element('direction', {'placement': 'below'})
            dtype = ET.SubElement(direction, 'direction-type')
            ET.SubElement(dtype, 'pedal', {'type': 'start' if value else 'stop', 'line': 'yes', 'number': '1'})
            ET.SubElement(direction, 'offset', {'sound': 'yes'}).text = str(round((offset-start)*divisions))
            # Before notes: offset is relative to the beginning of this measure.
            index = next((i for i,c in enumerate(measure) if c.tag not in ('attributes','print')), len(measure))
            # Preserve stop/start order on harmony changes.
            while index < len(measure) and measure[index].get('data-resonance') == 'yes': index += 1
            direction.set('data-resonance', 'yes')
            measure.insert(index, direction)
        for d in xml_part.iter('direction'): d.attrib.pop('data-resonance', None)
    tree.write(path, encoding='utf-8', xml_declaration=True)


def read_pedals(path, score):
    """Read exact standard XML pedal offsets (including releases after last note)."""
    for xml_part, part in zip(ET.parse(path).findall('part'), score.parts, strict=True):
        at = 0.; divisions = 1; events = []
        for measure in xml_part.findall('measure'):
            cursor = end = 0
            divisions = int(measure.findtext('attributes/divisions', divisions))
            for child in measure:
                dur = int(child.findtext('duration', '0'))
                if child.tag == 'backup': cursor -= dur
                elif child.tag == 'forward': cursor += dur
                elif child.tag == 'note' and child.find('chord') is None: cursor += dur
                elif child.tag == 'direction':
                    pedal = child.find('direction-type/pedal')
                    if pedal is not None:
                        offset = at + (cursor + float(child.findtext('offset','0'))) / divisions
                        kind = pedal.get('type')
                        if kind in ('stop','change'): events.append((offset,0))
                        if kind in ('start','change'): events.append((offset,127))
                end = max(end,cursor)
            at += end/divisions
        part.editorial.sustain_pedal = events
    return score


def copy_slurs(source, target):
    from music21 import spanner
    notes = {float(n.offset): n for n in target.flatten().notes}
    for slur in source.recurse().getElementsByClass(spanner.Slur):
        elements = slur.getSpannedElements()
        if not elements: continue
        a = float(elements[0].getOffsetInHierarchy(source))
        b = float(elements[-1].getOffsetInHierarchy(source))
        if a in notes and b in notes and a < b:
            target.insert(0, spanner.Slur(notes[a],notes[b]))
