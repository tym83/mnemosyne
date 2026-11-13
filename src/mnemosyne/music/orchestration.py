"""Deterministic, explicit orchestration of sounding musical lines.

This is a configurable feasibility/balance heuristic, not an artistic critic.
No event is silently dropped, no instrument or articulation silently replaced.
"""
from dataclasses import dataclass, asdict
from copy import deepcopy
import math
from music21 import note, stream, metadata, meter, tempo, dynamics, expressions, spanner
from .instrumentarium import REGISTRY, ensemble, notation_instrument, notation_clef, sample_patch, velocity_limits
from .schools.common import put, finish

ROLES = {'melody','bass','harmony_pad','counter_line','figuration','cluster_field','percussion_layer'}


@dataclass(frozen=True)
class Event:
    at: float
    duration: float
    pitches: tuple[float, ...]
    velocity: int = 64
    technique: str | None = None
    glide: tuple[float, float] | None = None


@dataclass(frozen=True)
class Line:
    id: str
    role: str
    events: tuple[Event, ...]
    register: tuple[float, float]
    density: float = .5
    colour: str | None = None
    instrument: str | None = None


def school_lines(score, plan):
    """Retain a grammar's pitches, rhythms, dynamics and continuous glissandi.

    Grammar voices are material, not playback instruments. Optional line_roles,
    line_colours and line_instruments make the person's orchestration explicit.
    """
    from .schools.performance import sounding_events
    from music21 import articulations
    result = []
    for i,part in enumerate(score.parts):
        source_notes = list(part.flatten().notes)
        events = []
        for at,length,pitches,strength,glide in sounding_events(part):
            source = next((n for n in source_notes if abs(float(n.offset)-at)<1e-7),None)
            tech = None
            if source is not None and any(isinstance(a,articulations.Staccato) for a in source.articulations):
                tech = 'staccato'
            events.append(Event(at,length,tuple(pitches),strength,tech,glide))
        if not events:
            continue
        pitches = [p for e in events for p in e.pitches]
        role = plan.get('line_roles',{}).get(str(i),'bass' if max(pitches)<60 else 'melody' if i==0 else 'counter_line')
        if plan['school'] in ('micropolyphony','sonorism','stochastic'):
            role = plan.get('line_roles',{}).get(str(i),'cluster_field')
        result.append(Line(str(i),role,tuple(events),(min(pitches),max(pitches)),
                           min(1,len(events)/max(1,float(part.highestTime))),
                           plan.get('line_colours',{}).get(str(i),plan.get('colour')),
                           plan.get('line_instruments',{}).get(str(i))))
    return result


def orchestrate(lines, plan):
    """Return sounding score + audit trail, with one lane per player/divisi group.

    Assignment is stable and range-first. Explicit instrument requests never
    change. Brass accompaniment is attenuated, winds get real breathing gaps,
    strings get bow changes; density and colour rank eligible players. Optional
    doubling is confined to loud lines and range-compatible unused players.
    """
    for field in ('duration','tempo'):
        value=plan.get(field)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f'{field} must be positive and finite')
    lines=list(lines)
    if len({line.id for line in lines})!=len(lines):
        raise ValueError('Musical line ids must be unique')
    required=set(plan.get('required_techniques',[]))
    realized={event.technique for line in lines for event in line.events}
    if not required <= realized:
        raise ValueError('Required techniques are not realized by the supplied lines: '+', '.join(sorted(required-realized)))
    players = ensemble(plan.get('orchestration',plan['ensemble']))
    lanes = []
    for p in players:
        for div in range(p.divisi):
            lanes.append({'player':p,'id':p.id+(f'-div{div+1}' if p.divisi>1 else ''),
                          'events':[],'divisi':div+1})
    audit = []
    total = plan['duration']*plan['tempo']/60
    # Allocate low-register lines first: bass desks must not be consumed by
    # material that higher instruments can play. Stable ties preserve plan order.
    for line in sorted(lines,key=lambda line:(line.instrument is None,line.register[0])):
        if line.role not in ROLES or not 0 < line.density <= 1:
            raise ValueError(f'Invalid line role/density: {line.id}')
        for e in line.events:
            if (not e.pitches or any(not math.isfinite(p) or not line.register[0]<=p<=line.register[1] for p in e.pitches)
                    or not math.isfinite(e.at) or not math.isfinite(e.duration) or e.at<0 or e.duration<=0
                    or e.at+e.duration>total+1e-6 or not 1<=e.velocity<=127):
                raise ValueError(f'Invalid event in line {line.id}: {e}')
            if e.technique=='glissando' and not e.glide:
                raise ValueError('A glissando needs an explicit target and duration')
            if e.glide and (len(e.glide)!=2 or not all(math.isfinite(x) for x in e.glide) or not 0<e.glide[0]<e.duration or abs(e.glide[1])>11):
                raise ValueError('Invalid or unsupported glissando trajectory')
            def eligible(lane, pitches):
                p=lane['player']; spec=p.spec
                if line.instrument and p.instrument != line.instrument:
                    return False
                if bool(spec.get('unpitched')) != (line.role=='percussion_layer'):
                    return False
                if e.glide and spec['family']!='strings' and p.instrument not in ('trombone','bass_trombone'):
                    return False
                if len(pitches)>spec['polyphony']:
                    return False
                technique=e.technique or ('arco' if spec['family']=='strings' else 'sustain')
                if technique=='staccato' and spec['family'] in ('keyboard','plucked','percussion'):
                    technique='sustain'
                zones=spec['samples'].get('key_ranges',{}).get(technique,[])
                if zones and not all(any(a<=round(pitch)<=b for a,b in zones) for pitch in pitches):
                    return False
                if not all(spec['range'][0]<=pitch<=spec['range'][1] for pitch in pitches):
                    return False
                if e.glide and not all(spec['range'][0]<=pitch+e.glide[1]<=spec['range'][1] for pitch in pitches):
                    return False
                return not any(e.at<other['at']+other['duration']-1e-8 and other['at']<e.at+e.duration-1e-8 for other in lane['events'])
            def rank(lane):
                p=lane['player']; spec=p.spec
                comfortable=sum(spec['comfortable'][0]<=x<=spec['comfortable'][1] for x in e.pitches)/len(e.pitches)
                colour=2 if line.colour in spec['colours'] else 0
                role=1 if ((line.role=='bass' and spec['comfortable'][0]<48) or
                           (line.role in ('cluster_field','harmony_pad') and spec['section']) or
                           (line.role=='figuration' and spec['family'] in ('keyboard','plucked','woodwinds'))) else 0
                penalty=2 if spec['family']=='brass' and e.velocity<65 and line.role!='melody' else 0
                # Stable balancing across players; no global/random state.
                affinity=20 if any(event['line']==line.id for event in lane['events']) else 0
                return (penalty-colour-role-comfortable-affinity,len(lane['events']),lanes.index(lane))
            # Keep playable chords on one instrument; otherwise split as divisi.
            candidates=sorted((l for l in lanes if eligible(l,e.pitches)),key=rank)
            targets=[]
            if candidates:
                targets=[(candidates[0],e.pitches)]
            else:
                for pitch in e.pitches:
                    candidates=sorted((l for l in lanes if eligible(l,(pitch,)) and all(l is not used for used,_ in targets)),key=rank)
                    if not candidates:
                        raise ValueError(f'No playable available player for line {line.id}, {pitch} at {e.at}; expand ensemble or revise plan')
                    targets.append((candidates[0],(pitch,)))
            if plan.get('doublings',False) and e.velocity>=90 and line.role in ('melody','bass') and len(e.pitches)==1:
                candidates=sorted((l for l in lanes if eligible(l,e.pitches) and all(l is not used for used,_ in targets)),key=rank)
                if candidates:
                    targets.append((candidates[0],e.pitches))
            for lane,pitches in targets:
                p=lane['player']; spec=p.spec
                technique=e.technique or ('arco' if spec['family']=='strings' else 'sustain')
                # Schools' staccato marks mean shortened notes; a separate patch
                # is optional for struck instruments whose only attack is short.
                if technique=='staccato' and spec['family'] in ('keyboard','percussion','plucked'):
                    technique='sustain'
                sample_patch(p.instrument,technique)
                bounds=[velocity_limits(p.instrument,x) for x in pitches]
                strength=max(max(a for a,b in bounds),min(e.velocity,min(b for a,b in bounds)))
                gain=spec['gain_db']+(-3 if spec['family']=='brass' and line.role not in ('melody','bass') else 0)
                # One section sample per divided group, energy compensated; do
                # not stack a full section at full level for every divisi lane.
                gain-=10*math.log10(p.divisi)
                phrase=spec['phrase_seconds']
                cap=phrase*plan['tempo']/60 if phrase else e.duration
                at=e.at; remaining=e.duration
                while remaining>1e-8:
                    dur=min(cap,remaining)
                    breath=spec['family'] in ('woodwinds','brass','voice')
                    gap=.25 if breath and dur>=2 else 0
                    item={'at':at,'duration':dur-gap,'pitches':pitches,'velocity':strength,
                          'technique':technique,'gain_db':gain,'line':line.id,'role':line.role,
                          'glide':e.glide if at==e.at else None}
                    if e.glide and e.duration>cap:
                        raise ValueError('Glissando exceeds phrase limit; split explicitly in plan')
                    lane['events'].append(item)
                    audit.append({'line':line.id,'player':lane['id'],'at':at,'technique':technique,
                                  'velocity_requested':e.velocity,'velocity':strength,'breath_quarters':gap})
                    at+=dur;remaining-=dur
    score=stream.Score(id='orchestration');score.atSoundingPitch=True
    score.metadata=metadata.Metadata(title=plan.get('title','Instrumentarium'))
    for lane in lanes:
        p=lane['player']; part=stream.Part(id=lane['id']);part.partName=lane['id'].replace('_',' ')
        part.insert(0,notation_instrument(p.instrument));part.insert(0,notation_clef(p.instrument))
        # A plan may change meter between sections; bars are cut by these signatures.
        for at,signature in plan.get('meters',[(0,'4/4')]):
            part.insert(float(at),meter.TimeSignature(signature))
        part.insert(0,tempo.MetronomeMark(number=plan['tempo']))
        for event in sorted(lane['events'],key=lambda e:e['at']):
            at=event['at'];dur=event['duration'];pitches=event['pitches']
            part.insert(at,expressions.TextExpression(event['technique']))
            # Explicit velocities survive notation dynamics independently.
            labels=['ppp','pp','p','mp','mf','f','ff','fff']
            label=labels[min(7,max(0,round((event['velocity']-16)/16)))]
            part.insert(at,dynamics.Dynamic(label))
            glide=event['glide']
            if p.spec.get('unpitched'):
                n=note.Unpitched(quarterLength=dur);n.displayStep='C';n.displayOctave=5
                n.volume.velocity=event['velocity'];part.insert(at,n)
            elif glide:
                split,delta=glide
                a=put(part,at,split,pitches)
                b=put(part,at+split,dur-split,tuple(x+delta for x in pitches))
                part.insert(at,spanner.Glissando(a,b,lineType='solid'))
            else:
                n=put(part,at,dur,pitches)
                n.volume.velocity=event['velocity']
        score.insert(0,part)
    finish(score,total)
    return score, {'version':1,'players':[{'id':l['id'],'instrument':l['player'].instrument,
        'players':l['player'].players//l['player'].divisi + int(l['divisi']<=l['player'].players%l['player'].divisi),'divisi':l['player'].divisi,'pan':l['player'].pan,
        'events':l['events']} for l in lanes], 'decisions':audit}


def orchestrate_existing(score, settings=None):
    """Route an existing constant-tempo movement through the same layer.

    Retain the exact source in the plan. A changing tempo map is rejected, not
    silently flattened: that needs an explicit timing-capable orchestration plan.
    """
    score=score.toSoundingPitch()
    boundaries=score.metronomeMarkBoundaries()
    bpms={mark.getQuarterBPM() for start,end,mark in boundaries if end>start}
    if len(bpms)!=1:
        raise ValueError('Native orchestration of an existing movement requires one tempo; preserve or explicitly resolve its tempo map first')
    bpm=bpms.pop()
    if not bpm or not math.isfinite(bpm):raise ValueError('Invalid movement tempo')
    plan={'school':'symphony','ensemble':'symphony_orchestra','tempo':bpm,
          'duration':float(score.highestTime)*60/bpm,'title':score.metadata.title if score.metadata else 'Symphony',
          'audio_profile':'native_sfz','source_musicxml':score.write('musicxml').read_text()}
    if settings:
        if any(k in settings for k in ('tempo','duration','school','source_musicxml')):
            raise ValueError('Orchestration settings cannot replace source timing/provenance')
        plan.update(settings)
    lines=school_lines(score,plan)
    orchestrated,assignment=orchestrate(lines,plan)
    return orchestrated,plan,assignment
