"""Sounding MIDI: per-part bends (+/-12 semitones), ties, chords and glissandi.

A channel can play a chord only when all its pitches have the same bend.
Reject incompatible chords rather than silently detuning their notes.
"""
import struct
from music21 import articulations, dynamics, spanner


def vlq(n):
    out = [n & 127]
    while n >> 7:
        n >>= 7
        out.insert(0, (n & 127)|128)
    return bytes(out)


def velocity(n):
    dynamic = n.getContextByClass(dynamics.Dynamic)
    return max(8, min(127, round(127*(dynamic.volumeScalar if dynamic else .5))))


def sounding_events(part):
    flat = part.flatten()
    notes = list(flat.notes)
    offsets = {id(n): float(flat.elementOffset(n)) for n in notes}
    merged = []
    for n in notes:
        pitches = tuple(p.ps for p in n.pitches)
        if n.tie and n.tie.type in ('continue', 'stop') and merged and merged[-1][3] == pitches:
            merged[-1][1] += float(n.quarterLength)
        else:
            merged.append([offsets[id(n)], float(n.quarterLength), n, pitches])
    glisses, consumed = {}, set()
    for g in part.recurse().getElementsByClass(spanner.Glissando):
        a, b = g.getSpannedElements()
        glisses[id(a)] = b
        consumed.add(id(b))
    for at, length, n, pitches in merged:
        if id(n) in consumed:
            continue
        # Editorial cents survive makeTies but intentionally are not in MusicXML.
        exact = getattr(n.editorial, 'just_pitch', None)
        pitches = (exact,) if exact is not None else pitches
        target = glisses.get(id(n))
        glide = None
        if target is not None:
            delta = target.pitch.ps-pitches[0]
            if abs(delta) > 11:
                raise ValueError('glissando exceeds safe bend range')
            target_at = offsets[id(target)]
            target_length = next((dur for onset, dur, obj, ps in merged if obj is target), float(target.quarterLength))
            glide = (target_at-at, delta)
            length = target_at-at+target_length
        elif any(isinstance(a, articulations.Staccato) for a in n.articulations):
            length *= .5
        yield at, length, pitches, velocity(n), glide


def write_midi(score, path, bpm, orchestral=False):
    if len(score.parts) > 15:
        raise ValueError('pitch-bend playback supports at most 15 parts')
    tracks = []
    for i, part in enumerate(score.parts):
        channel = i if i < 9 else i+1
        ins = part.recurse().getElementsByClass('Instrument').first()
        program = 48 if orchestral and ins.midiProgram == 40 else ins.midiProgram
        events = [(0, 0, bytes([0xC0|channel, program]))]
        for cc, value in ((101,0),(100,0),(6,12),(38,0),(101,127),(100,127),(10,round(25+77*i/max(1,len(score.parts)-1)))):
            events.append((0, 0, bytes([0xB0|channel, cc, value])))
        if i == 0:
            events.append((0, -1, b'\xff\x51\x03'+round(60000000/bpm).to_bytes(3,'big')))
        def bend(semitones):
            value = max(0, min(16383, 8192+round(semitones/12*8192)))
            return bytes([0xE0|channel, value & 127, (value >> 7) & 127])
        for at, length, pitches, strength, glide in sounding_events(part):
            tick = round(at*960)
            keys = [round(p) for p in pitches]
            deviations = [p-key for p,key in zip(pitches,keys)]
            if max(deviations)-min(deviations) > 1e-6:
                raise ValueError('chord requires incompatible simultaneous pitch bends')
            base = deviations[0]
            events.append((tick, 1, bend(base)))
            if glide:
                duration, delta = glide
                for k in range(1, 129):
                    events.append((tick+round(duration*960*k/128), 3, bend(base+delta*k/128)))
            for key in keys:
                events.append((tick, 2, bytes([0x90|channel, key, strength])))
                events.append((tick+round(length*960), 0, bytes([0x80|channel, key, 0])))
        events.append((round(float(part.highestTime)*960), 9, b'\xff\x2f\x00'))
        data, previous = bytearray(), 0
        for tick, priority, msg in sorted(events, key=lambda e:(e[0], e[1])):
            data.extend(vlq(tick-previous)+msg)
            previous = tick
        tracks.append(b'MTrk'+struct.pack('>I',len(data))+data)
    path.write_bytes(b'MThd'+struct.pack('>IHHH',6,1,len(tracks),960)+b''.join(tracks))
