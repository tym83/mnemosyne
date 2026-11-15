"""Versioned plan contract; all pitches and ranges are sounding MIDI notes."""
from fractions import Fraction
import math
from .choices import ChoiceSource, SeededChoices
from music21 import chord, clef, dynamics, expressions, instrument, metadata, meter, note, stream, tempo

VERSION = 2
from ..instrumentarium import REGISTRY, LEGACY_VOICES, ENSEMBLE_DATA, notation_instrument
# Version-2 grammar voices remain stable; playback ensembles live in ensembles.yaml.
ENSEMBLES = LEGACY_VOICES
RANGES = {name: tuple(spec['range']) for name,spec in REGISTRY.items()}
RANGES.update({name: tuple(bounds) for name,bounds in ENSEMBLE_DATA.get('legacy_ranges',{}).items()})
CLASSES = {name: (lambda name=name: notation_instrument(name)) for name in REGISTRY}
CHARACTERS = {'still': 'pp', 'flowing': 'p', 'agitated': 'f', 'luminous': 'mp', 'dissolving': 'ppp'}


def validate(plan):
    if plan.get('ensemble') not in ENSEMBLES:
        raise ValueError(f'ensemble must be one of {list(ENSEMBLES)}')
    for name in ('duration', 'tempo'):
        value = plan.get(name)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be positive and finite')
    total = Fraction(str(plan['duration'])) * Fraction(str(plan['tempo'])) / 60
    if total < 4 or (total * 4).denominator != 1:
        raise ValueError('duration * tempo / 60 must be >= 4 quarters and on a sixteenth grid')
    sections = plan.get('form')
    if not isinstance(sections, list) or not sections:
        raise ValueError('form must be a nonempty list')
    durations = []
    for sec in sections:
        if sec.get('character') not in CHARACTERS:
            raise ValueError(f'character must be one of {list(CHARACTERS)}')
        d = sec.get('density')
        if not isinstance(d, (float,int)) or not math.isfinite(d) or not 0 < d <= 1:
            raise ValueError('density must be in (0,1]')
        reg = sec.get('register')
        if not isinstance(reg, list) or len(reg) != 2 or any(type(x) is not int for x in reg) or not 0 <= reg[0] < reg[1] <= 127:
            raise ValueError('register must be [low, high] sounding MIDI')
        length = Fraction(str(sec.get('duration', 0))) * Fraction(str(plan['tempo'])) / 60
        if length < 4 or (length*4).denominator != 1:
            raise ValueError('each section must be >= 4 quarters on a sixteenth grid')
        durations.append(length)
        for name in ENSEMBLES[plan['ensemble']]:
            low, high = RANGES[name]
            if min(high,reg[1])-max(low,reg[0]) < (1 if plan.get('school') == 'micropolyphony' else 11):
                raise ValueError(f'register must overlap {name} range by at least an octave')
    if sum(durations) != total:
        raise ValueError('section durations must sum to duration')
    return total, durations


def setup(plan, seed, school, *, choices: ChoiceSource | None = None):
    total, lengths = validate(plan)
    rng = SeededChoices(seed) if choices is None else choices
    score = stream.Score(id=school)
    score.atSoundingPitch = True
    score.metadata = metadata.Metadata(title=plan.get('title', school))
    sections, start = [], Fraction(0)
    for sec, length in zip(plan['form'], lengths):
        sections.append((start, start+length, sec))
        start += length
    for i, name in enumerate(ENSEMBLES[plan['ensemble']]):
        part = stream.Part(id=f'{name}-{i}')
        part.partName = f'{name.replace("_", " ")} {i+1}'
        ins = CLASSES[name]()
        ins.instrumentId = f'instrument-{i}'
        ins.midiChannel = i if i < 9 else i+1
        part.insert(0,ins)
        part.insert(0, clef.BassClef() if name in ('cello','bass','bass_voice') or (name=='piano' and i==1) else clef.AltoClef() if name=='viola' else clef.TrebleClef())
        part.insert(0,meter.TimeSignature('4/4'))
        part.insert(0,tempo.MetronomeMark(number=plan['tempo']))
        for a,b,sec in sections:
            part.insert(a, dynamics.Dynamic(sec.get('dynamic', CHARACTERS[sec['character']])))
            part.insert(a, expressions.TextExpression(sec['character']))
        score.insert(0,part)
    return score, rng, sections, total


def limits(name, sec):
    low, high = RANGES[name]
    return max(low,sec['register'][0]), min(high,sec['register'][1])


def nearest(pc, target, low, high):
    return min((p for p in range(low,high+1) if p%12 == pc%12), key=lambda p: (abs(p-target),p))


def put(part, at, length, pitch, articulation=None):
    if length <= 0:
        return None
    if isinstance(pitch,(list,tuple)) and len(pitch)==1:
        pitch=pitch[0]
    n = note.Rest(quarterLength=length) if pitch is None else (chord.Chord([note.Note(float(p)) for p in pitch], quarterLength=length) if isinstance(pitch, (list, tuple)) else note.Note(float(pitch),quarterLength=length))
    # music21's diatonic instrument transpose loses 1.5-semitone accidentals.
    # Equivalent half-flat spellings survive MusicXML transposition exactly.
    for written in n.pitches:
        if written.accidental and abs(written.accidental.alter) > 1:
            written.getEnharmonic(inPlace=True)
    if articulation and pitch is not None:
        n.articulations.append(articulation)
    part.insert(at,n)
    return n


def finish(score, total):
    # Explicit rests fill every silent interval, including final silence.
    for part in score.parts:
        cursor = Fraction(0)
        for event in sorted(part.notesAndRests, key=lambda n:n.offset):
            # music21 keeps whole offsets as floats and others as Fractions: compare exactly, or
            # 8.0 + 4/3 (a float) lands past a note at 28/3 and reads as an overlap.
            offset = Fraction(event.offset)
            if offset < cursor:
                raise ValueError(f'overlapping events in a monophonic part {part.id} at {float(offset)}')
            if offset > cursor:
                put(part,cursor,event.offset-cursor,None)
            cursor = offset+Fraction(event.quarterLength)
        if cursor < total:
            put(part,cursor,total-cursor,None)
    score.makeMeasures(inPlace=True)
    score.makeTies(inPlace=True)
    return score


def analyze(score, plan):
    total, _ = validate(plan)
    result = []
    for part,name in zip(score.parts, ENSEMBLES[plan['ensemble']], strict=True):
        pitches = [p.ps for n in part.recurse().notes for p in n.pitches]
        low,high = RANGES[name]
        if not pitches or any(not low <= p <= high for p in pitches):
            raise ValueError(f'empty or out-of-range part: {part.id}')
        if abs(float(part.highestTime-total)) > 1e-8:
            raise ValueError(f'wrong duration: {part.id}')
        result.append({'part':part.id,'notes':len(pitches),'range':[min(pitches),max(pitches)],'quarters':float(part.highestTime)})
    return {'score_seconds':float(total)*60/plan['tempo'],'parts':result,'out_of_range':0,'empty_parts':0}
