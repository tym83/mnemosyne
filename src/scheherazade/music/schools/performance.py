"""Sounding-pitch MIDI with tied durations, dynamics and continuous glissandi.

Each monophonic part owns a channel. Bend range is explicitly set to +/-12
semitones. The score's glissando pair becomes one held, continuously bent note.
"""
import struct
from music21 import articulations, dynamics, spanner


def vlq(n):
    out = [n & 127]
    while n >> 7:
        n >>= 7
        out.insert(0,(n & 127)|128)
    return bytes(out)


def write_midi(score, path, bpm, orchestral=False):
    tracks = []
    for i,part in enumerate(score.parts):
        channel = i if i<9 else i+1
        ins = part.recurse().getElementsByClass("Instrument").first()
        program = 48 if orchestral and ins.midiProgram==40 else ins.midiProgram
        events = [(0,0,bytes([0xC0|channel,program]))]
        for cc,value in ((101,0),(100,0),(6,12),(38,0),(101,127),(100,127),(10,round(25+77*i/max(1,len(score.parts)-1)))):
            events.append((0,0,bytes([0xB0|channel,cc,value])))
        if i==0:
            events.append((0,-1,b'\xff\x51\x03'+round(60000000/bpm).to_bytes(3,'big')))
        flat = part.flatten()
        notes = list(flat.notes)
        offsets = {id(n):float(flat.elementOffset(n)) for n in notes}
        merged = []
        for n in notes:
            at = offsets[id(n)]
            length = float(n.quarterLength)
            if n.tie and n.tie.type in ('continue','stop') and merged and merged[-1][2].pitch.midi==n.pitch.midi:
                merged[-1][1] += length
            else:
                merged.append([at,length,n])
        glisses = {}
        consumed = set()
        for g in part.recurse().getElementsByClass(spanner.Glissando):
            a,b = g.getSpannedElements()
            glisses[id(a)] = b
            consumed.add(id(b))
        for at,length,n in merged:
            if id(n) in consumed:
                continue
            tick = round(at*480)
            dynamic = n.getContextByClass(dynamics.Dynamic)
            velocity = max(20,min(110,round(127*(dynamic.volumeScalar if dynamic else .5))))
            target = glisses.get(id(n))
            bend = lambda value: bytes([0xE0|channel,value & 127,(value>>7)&127])
            events.append((tick,1,bend(8192)))
            if target is not None:
                delta = target.pitch.midi-n.pitch.midi
                if abs(delta)>12:
                    raise ValueError('glissando exceeds configured pitch bend range')
                target_at = offsets[id(target)]
                # Include all tied fragments of the destination.
                target_length = next((dur for onset,dur,obj in merged if obj is target),float(target.quarterLength))
                length = target_at-at+target_length
                for k in range(1,33):
                    when = tick+round((target_at-at)*480*k/32)
                    value = max(0,min(16383,8192+round(delta/12*8192*k/32)))
                    events.append((when,3,bend(value)))
            elif any(isinstance(a,articulations.Staccato) for a in n.articulations):
                length *= .5
            events.append((tick,2,bytes([0x90|channel,n.pitch.midi,velocity])))
            events.append((tick+round(length*480),0,bytes([0x80|channel,n.pitch.midi,0])))
        events.append((round(float(part.highestTime)*480),9,b'\xff\x2f\x00'))
        data = bytearray()
        previous = 0
        for tick,priority,msg in sorted(events,key=lambda e:(e[0],e[1])):
            data.extend(vlq(tick-previous)+msg)
            previous = tick
        tracks.append(b'MTrk'+struct.pack('>I',len(data))+data)
    path.write_bytes(b'MThd'+struct.pack('>IHHH',6,1,len(tracks),480)+b''.join(tracks))
