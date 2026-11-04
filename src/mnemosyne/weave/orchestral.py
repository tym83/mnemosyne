"""Octave-order surface channel v1, reconstructed from sounding harp notes.

One bit per beat: two eighths, same pitch class, one octave apart. Authenticated
context covers note pitches/timing, part order and tempo, not engraving metadata.
PDF/audio decoding and robust survival through editors are not promised.
"""
import hashlib
import json
import struct
from . import arithmetic, payload, DecodeError


def slots(scores):
    result = []
    for score in scores:
        for part in score.parts:
            ins = part.recurse().getElementsByClass('Instrument').first()
            if ins is None or ins.instrumentName != 'harp':
                continue
            ns = list(part.flatten().notes)
            for a, b in zip(ns[::2], ns[1::2]):
                if (len(a.pitches) != 1 or len(b.pitches) != 1 or
                    a.quarterLength != .5 or b.quarterLength != .5 or
                    float(a.offset) % 1 or b.offset != a.offset + .5 or
                    abs(a.pitch.ps-b.pitch.ps) != 12):
                    raise DecodeError('invalid harp surface cell')
                result.append((a, b))
            if len(ns) % 2:
                raise DecodeError('incomplete harp cell')
    return result


def context(scores):
    parts = []; tempi = []; offset = 0
    for score in scores:
        for pi, part in enumerate(score.parts):
            ins = part.recurse().getElementsByClass('Instrument').first()
            if pi == len(parts):parts.append([ins.instrumentName, []])
            if parts[pi][0] != ins.instrumentName:raise DecodeError('inconsistent orchestra')
            carrier = {}
            if ins.instrumentName == 'harp':
                for a,b in slots([score]):
                    carrier[float(a.offset)] = carrier[float(b.offset)] = min(a.pitch.ps,b.pitch.ps)
            events=parts[pi][1]
            def split(at, duration, pitches):
                # Engravers split tied notes and compound rests within beats.
                # Canonical 4/4 cells depend on sounding duration, not spelling.
                while duration>1e-7:
                    size=min(duration,4-at%4)
                    events.append((offset+float(at),float(size),pitches))
                    at+=size;duration-=size
            cursor=0
            for n in part.stripTies().flatten().notes:
                at=float(n.offset);duration=float(n.quarterLength)
                if at<cursor-1e-7:raise DecodeError('overlapping surface score voice')
                if at>cursor:split(cursor,at-cursor,[])
                split(at,duration,[carrier[at]] if at in carrier else [p.ps for p in n.pitches])
                cursor=at+duration
            if cursor<part.highestTime:split(cursor,float(part.highestTime)-cursor,[])
        for a,b,m in score.metronomeMarkBoundaries():
            item=[offset+float(a),offset+float(b),m.getQuarterBPM()]
            if tempi and tempi[-1][1]==item[0] and tempi[-1][2]==item[2]:tempi[-1][1]=item[1]
            else:tempi.append(item)
        offset += float(score.highestTime)
    return json.dumps([parts,tempi],separators=(',',':')).encode()


def encode(scores, data, recipient):
    ss = slots(scores); size = arithmetic.capacity([2]*len(ss))
    frame = payload.seal(data,recipient,context=context(scores))
    if len(frame)>size:
        raise ValueError(f'backup needs {len(frame)} bytes; surface holds {size}')
    digits = arithmetic.encode(frame.ljust(size,b'\0'),[2]*len(ss))
    for (a,b),bit in zip(ss,digits):
        low = min(a.pitch.ps,b.pitch.ps)
        a.pitch.ps = low+12*bit; b.pitch.ps = low+12*(1-bit)
    return {'channel':'harp-octave-order-v1','slots':len(ss),'capacity_bytes':size,
            'envelope_bytes':len(frame),'payload_bytes':len(data),
            'payload_sha256':hashlib.sha256(data).hexdigest(),
            'context_sha256':hashlib.sha256(context(scores)).hexdigest(),
            'envelope_sha256':hashlib.sha256(frame).hexdigest(),
            'scope':'MusicXML note surface; PDF/audio are renditions; no whole-cluster claim'}


def envelope(scores):
    """Recover the complete encrypted envelope; no key or sidecar is required."""
    ss=slots(scores);size=arithmetic.capacity([2]*len(ss))
    block=arithmetic.decode([int(a.pitch.ps>b.pitch.ps) for a,b in ss],[2]*len(ss),size)
    if len(block)<8:raise DecodeError('truncated envelope')
    length=struct.unpack('>I',block[4:8])[0]
    if not payload.OVERHEAD<=length<=len(block) or any(block[length:]):
        raise DecodeError('invalid envelope length/padding')
    return block[:length]


def decode(scores, recipient):
    return payload.open_envelope(envelope(scores),recipient,context=context(scores))


def main():
    import argparse
    from pathlib import Path
    from music21 import converter
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scores',nargs='+',type=Path,help='Combined score or movement scores in playback order')
    keys=parser.add_mutually_exclusive_group(required=True)
    keys.add_argument('--recipient-key',type=Path,help='External 32-byte recipient private key')
    keys.add_argument('--public-test-fixture',action='store_true',help='Only for the synthetic public demo')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    raw=(hashlib.sha256(b'symphony-public-test-fixture-v1').digest() if args.public_test_fixture
         else args.recipient_key.read_bytes())
    key=X25519PrivateKey.from_private_bytes(raw)
    data=decode([converter.parse(p).toSoundingPitch() for p in args.scores],key)
    args.out.write_bytes(data)
    print(f'Recovered {len(data)} authenticated bytes; SHA-256 {hashlib.sha256(data).hexdigest()}')


if __name__=='__main__':main()
