"""Sounding MIDI: per-part bends (+/-12 semitones), ties, chords and glissandi.

A channel can play a chord only when all its pitches have the same bend.
Reject incompatible chords rather than silently detuning their notes.
"""
import struct
from music21 import articulations, dynamics, spanner, note


def vlq(n):
    out = [n & 127]
    while n >> 7:
        n >>= 7
        out.insert(0, (n & 127)|128)
    return bytes(out)


def velocity(n):
    if n.volume.velocity is not None:
        return max(1, min(127, int(n.volume.velocity)))
    dynamic = n.getContextByClass(dynamics.Dynamic)
    return max(8, min(127, round(127*(dynamic.volumeScalar if dynamic else .5))))


def sounding_events(part, bpm=None):
    flat = part.flatten()
    notes = list(flat.notes)
    offsets = {id(n): float(flat.elementOffset(n)) for n in notes}
    merged = []
    for n in notes:
        pitches = tuple(p.ps for p in n.pitches)
        if isinstance(n, note.Unpitched):
            ins=part.recurse().getElementsByClass('Instrument').first()
            pitches=(getattr(ins, "percMapPitch", None) if getattr(ins, "percMapPitch", None) is not None else 35,)
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
        if bpm is not None and glide is None:
            # Only contiguous, same-voice slurred notes with a different key can
            # overlap safely on one MIDI channel. Never bridge a written rest.
            for slur in part.recurse().getElementsByClass(spanner.Slur):
                members = slur.getSpannedElements()
                if not members or n is members[-1]:
                    continue
                start = offsets.get(id(members[0]), -1)
                end = offsets.get(id(members[-1]), -1)
                voice = n.getContextByClass('Voice')
                nxt = next((other for other in notes if offsets[id(other)] > at
                            and other.getContextByClass('Voice') is voice), None)
                if (start <= at < end and nxt is not None
                        and abs(offsets[id(nxt)] - at - length) < 1e-7
                        and not set(pitches) & {p.ps for p in nxt.pitches}
                        and all(abs(p-round(p)) < 1e-7 for p in (*pitches, *(p.ps for p in nxt.pitches)))):
                    length += min(.03*bpm/60, float(nxt.quarterLength)/4)
                    break
        yield at, length, pitches, velocity(n), glide


def write_midi(score, path, bpm, orchestral=False, *, tail_seconds=0):
    tracks = []
    for i, part in enumerate(score.parts):
        local_channel = i % 15
        channel = local_channel if local_channel < 9 else local_channel+1
        ins = part.recurse().getElementsByClass('Instrument').first()
        if getattr(ins, 'midiChannel', None) == 9:
            channel=9
        program = 48 if orchestral and ins.midiProgram == 40 else ins.midiProgram
        events = [(0, -2, b'\xff\x21\x01'+bytes([i//15]))]
        # MusicXML percussion can specify an unpitched key without a program.
        if program is not None:
            events.append((0, 0, bytes([0xC0|channel, program])))
        elif channel != 9:
            raise ValueError(f'Missing MIDI program for {part.id}')
        for cc, value in ((101,0),(100,0),(6,12),(38,0),(101,127),(100,127),(10,(64 if len(score.parts)==1 else round(25+77*i/max(1,len(score.parts)-1))))):
            events.append((0, 0, bytes([0xB0|channel, cc, value])))
        if i == 0:
            events.append((0, -1, b'\xff\x51\x03'+round(60000000/bpm).to_bytes(3,'big')))
        def bend(semitones):
            value = max(0, min(16383, 8192+round(semitones/12*8192)))
            return bytes([0xE0|channel, value & 127, (value >> 7) & 127])
        # CC11 realizes sustained-tone dynamics; decoding still uses source XML,
        # because standard MIDI quantizes expression to seven bits.
        curve = getattr(part.editorial, 'school_expression', None)
        if curve:
            for at, gain in curve:
                events.append((round(at*960), 1, bytes([0xB0|channel, 11, max(0,min(127,round(96*gain)))])))
        from ..resonance import pedal_events
        for at, value in pedal_events(part):
            events.append((round(at*960), -1, bytes([0xB0|channel, 64, value])))
        for at, length, pitches, strength, glide in sounding_events(part, bpm):
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
        events.append((max(round((float(part.highestTime)+tail_seconds*bpm/60)*960), max(e[0] for e in events)), 9, b'\xff\x2f\x00'))
        data, previous = bytearray(), 0
        for tick, priority, msg in sorted(events, key=lambda e:(e[0], e[1])):
            data.extend(vlq(tick-previous)+msg)
            previous = tick
        tracks.append(b'MTrk'+struct.pack('>I',len(data))+data)
    path.write_bytes(b'MThd'+struct.pack('>IHHH',6,1,len(tracks),960)+b''.join(tracks))
