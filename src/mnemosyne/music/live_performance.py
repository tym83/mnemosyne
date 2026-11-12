"""Deterministic audio-only performance. Never edits a score or backup values.

Notated slurs and rests delimit dynamic phrases; the shared eight-beat tempo
clock is a fallback, not harmonic analysis. All times are quarter notes.
"""
import math
import numpy as np


def profile(school):
    # swell: how far a held tone opens after the attack and fades before release.
    # It is a device the plan asks for (held_swell), never the default sound.
    if school in ('ustvolskaya', 'reich', 'additive', 'process', 'phase'):
        return dict(dynamics=0., timing=0., cadence=0., soft=1., swell=0.)
    if school == 'feldman':
        return dict(dynamics=.015, timing=.003, cadence=.005, soft=.50, swell=.15)
    if school == 'tintinnabuli':
        return dict(dynamics=.15, timing=.008, cadence=.018, soft=1., swell=.35)
    return dict(dynamics=.4, timing=.016, cadence=.045, soft=1., swell=.45)


SHAPED = ('strings', 'woodwinds', 'brass', 'voice')


def note_shape(t, seconds, swell):
    """Level of a held tone t seconds after its onset: players open a long
    note after the attack and let it fade into the release, never hold it flat."""
    if seconds < .6 or not swell:
        return 1.
    rise, fall = min(.35*seconds, 1.2), min(.4*seconds, 1.8)
    if t < rise:
        return 1-swell/2*math.cos(math.pi/2*t/rise)
    if t > seconds-fall:
        return 1-swell*math.sin(math.pi/2*min(1., (t-seconds+fall)/fall))
    return 1.


def held_level(at, notes, bpm, swell):
    sounding = [note_shape((at-a)*60/bpm, n*60/bpm, swell) for a, n in notes if a <= at < a+n]
    return max(sounding, default=1.)


def family(part):
    from .instrumentarium import REGISTRY
    ins = part.recurse().getElementsByClass('Instrument').first()
    program = getattr(ins, 'midiProgram', None)
    return next((v['family'] for v in REGISTRY.values()
                 if v.get('gm_program') == program), 'other')


def warp(at, style):
    # Smooth, monotone, fixed phrase endpoints: no drift between sections/parts.
    phase = (at % 8) / 8
    return at - style['cadence'] * 8 * math.sin(2*math.pi*phase)/(2*math.pi)


def phrase_spans(part):
    """Read phrase evidence without changing notation or inventing harmony."""
    from music21 import spanner
    flat=part.flatten();notes=sorted(flat.notes,key=lambda n:float(n.offset))
    spans=[];start=end=None
    for n in notes:
        at=float(n.offset);off=at+float(n.quarterLength)
        if start is None:start,end=at,off
        elif at>end+.5 or at-start>=8:
            spans.append((start,end));start,end=at,off
        else:end=max(end,off)
    if start is not None:spans.append((start,end))
    explicit=[]
    for slur in part.recurse().getElementsByClass(spanner.Slur):
        members=slur.getSpannedElements()
        if members:
            a=float(members[0].getOffsetInHierarchy(part))
            b=float(members[-1].getOffsetInHierarchy(part))+float(members[-1].quarterLength)
            if b>a:explicit.append((a,b))
    return explicit,spans


def phrase_phase(at,spans):
    for group in spans:
        for start,end in group:
            if start<=at<end:return (at-start)/max(end-start,1e-9)
    return 0.


def expression_points(part, bpm, school, held_swell=False):
    """Multiply woven expression by a phrase envelope; never replace its data."""
    style=profile(school)
    if not held_swell:style['swell']=0.
    spans=phrase_spans(part)
    curve=getattr(part.editorial,'school_expression',None)
    if not style['dynamics']:
        return [(at,max(0,min(127,round(96*gain)))) for at,gain in (curve or [])]
    knots,values=zip(*curve) if curve else ([0.],[1.])
    notes=[]
    if family(part) in SHAPED:
        from .schools.performance import sounding_events
        notes=[(a,n) for a,n,*_ in sounding_events(part,bpm)]
    result=[]
    for at in np.arange(0,float(part.highestTime)+.025*bpm/60,.05*bpm/60):
        shape=(1+style['dynamics']*math.sin(math.pi*phrase_phase(at,spans)))/(1+style['dynamics'])
        shape*=held_level(at,notes,bpm,style['swell'])
        level=(96 if curve else 127)*float(np.interp(at,knots,values))*shape
        result.append((warp(at,style),max(0,min(127,round(level)))))
    return result


def perform(events, part, bpm, school):
    """Return sounding events plus a machine-readable schedule audit.

    Equal onsets receive equal offsets (chords stay chords). Rests and repeated
    keys remain separate. Breath splits are audible rests, never hidden by
    legato. String bow changes use per-voice SFZ amplitude modulation instead
    of restarting recorded attacks.
    """
    style=profile(school);kind=family(part);events=list(events);spans=phrase_spans(part)
    out=[];audit=[]
    for i,(at,length,pitches,velocity,glide) in enumerate(events):
        phase=phrase_phase(at,spans)
        # Agogic motion, zero on phrase boundaries; deterministic without RNG.
        jitter=style['timing']*bpm/60*math.sin(at*2.39996323)*math.sin(math.pi*phase)
        start=max(0.,warp(at,style)+jitter)
        end=warp(at+length,style)+jitter
        strength=max(1,min(127,round(velocity*style['soft']*(1+style['dynamics']*math.sin(math.pi*phase)))))
        if kind in ('woodwinds','brass') and glide is None:
            limit=6*bpm/60;breath=.16*bpm/60
        else:limit=float('inf');breath=0.
        pieces=[];cursor=start
        while end-cursor>limit:
            pieces.append((cursor,limit));cursor+=limit+breath
        if end>cursor:pieces.append((cursor,end-cursor))
        for onset,duration in pieces:out.append((onset,duration,pitches,strength,glide))
        audit.append(dict(score_onset=at,played_onset=start,timing_ms=(start-at)*60000/bpm,
                          score_velocity=velocity,played_velocity=strength,
                          breath_breaks=max(0,len(pieces)-1),family=kind))
    # Preserve existing notated slur overlap after timing warp; do not infer slurs.
    for i in range(len(out)-1):
        a,b=out[i],out[i+1]
        original=next((e for e in events if e[2]==a[2] and abs(warp(e[0],style)-a[0])<.1),None)
        if original is None:continue
        following=next((e for e in events if e[0]>original[0]),None)
        if (following and original[0]+original[1]>following[0]+1e-6
                and not set(a[2]) & set(b[2]) and a[4] is None and b[4] is None):
            overlap=min(.06*bpm/60,b[1]/4)
            out[i]=(a[0],max(a[1],b[0]+overlap-a[0]),*a[2:])
    return out, audit


def vibrato_points(at,length,bpm,base=0.,depth_cents=12.):
    """Pitch wheel fallback for isolated monophonic notes; delay 0.45 s."""
    seconds=length*60/bpm
    if seconds<.8:return []
    result=[]
    for k in range(math.ceil(seconds*100)):
        t=k/100
        depth=depth_cents*min(1.,max(0.,(t-.45)/.35))
        result.append((at+t*bpm/60,base+depth/100*math.sin(2*math.pi*5.2*t)))
    result.append((at+length,base))
    return result


def seat(data,pan,kind,rate):
    """Stereo direct sound and explicit early reflections; no feedback.

    Farther desks have less direct sound and stronger delayed lateral energy.
    The hall convolution remains separate, preserving its measured IR.
    """
    depth={'strings':.25,'keyboard':.2,'woodwinds':.55,'brass':.8,'percussion':.9}.get(kind,.4)
    gains=np.array([math.sqrt(1-max(0,pan)),math.sqrt(1+min(0,pan))])
    direct=np.asarray(data)*gains*(1-.25*depth)
    result=direct.copy()
    taps=[(.017+.014*depth,.12+.08*depth),(.031+.021*depth,.08+.06*depth)]
    for seconds,gain in taps:
        delay=round(seconds*rate)
        if delay<len(data):result[delay:]+=direct[:-delay,::-1]*gain
    return result,dict(depth=depth,direct_gain=1-.25*depth,early_reflections=taps,
                       hall_send_gain=1+.8*depth)


def prepare_patch(source,destination,kind,*,legato=False):
    """Preserve native release/layer/RR opcodes, add per-voice performance.

    Fallback legato enters the existing loop, bypassing the recorded attack.
    It is a crossfade, never advertised as a recorded interval transition.
    Only enable on monophonic stems. Native legato regions take precedence.
    """
    import json
    from .native_bank import regions
    from .sample_sustain import audio_info
    zones=regions(source);native_legato=any(z['trigger']=='legato' for z in zones)
    rows=[];report=[]
    sustained=kind in ('strings','woodwinds','brass')
    for z in zones:
        op={**z['opcodes'],'sample':z['sample']}
        release=z['trigger'] in ('release','release_key')
        entry={'sample':z['sample'],'trigger':z['trigger'],'recorded_release':release,
               'velocity_range':[z['lovel'],z['hivel']],'rr':[z['seq_position'],z['seq_length']]}
        if sustained and not release:
            # Sample vibrato remains untouched; do not double its modulation.
            recorded_vibrato=any(s in z['sample'].lower() for s in ('vib','_vb'))
            if not recorded_vibrato and 'pitchlfo_depth' not in op:
                op.update(pitchlfo_freq='5.2',pitchlfo_depth='12',pitchlfo_delay='.45',pitchlfo_fade='.35')
                entry['vibrato']={'mode':'lfo','depth_cents':12,'delay_seconds':.45,'fade_seconds':.35}
            else:entry['vibrato']={'mode':'sample-or-native-lfo','onset':'library-defined'}
            if kind=='strings':
                # Small periodic bow-pressure relief, per voice (no MIDI retrigger).
                if 'amplfo_depth' not in op:op.update(amplfo_freq='.22',amplfo_depth='1.2',amplfo_delay='2')
                entry['bow_pressure']={'period_seconds':1/.22,'depth_db':1.2,'delay_seconds':2}
            if legato and not native_legato and z['trigger']=='attack' and 'loop_start' in op:
                first={**op,'trigger':'first'}
                rows.append(first)
                op={**op,'trigger':'legato','offset':op['loop_start'],'ampeg_attack':'.06'}
                entry['legato']='loop-entry-crossfade'
        rows.append(op);report.append(entry)
    if not sustained:
        # Keyboard release layers often depend on control defaults and custom
        # curves. Preserve those headers, not just flattened region opcodes.
        destination.write_text(source.read_text())
    else:
        import re
        headers = '\n'.join(m.group(0) for m in re.finditer(
            r'<(?:control|curve|effect)>[^<]*', source.read_text()))
        destination.write_text(headers+'\n'+'\n'.join('<region>\n'+'\n'.join(
            f'{k}={v}' for k,v in row.items()) for row in rows)+'\n')
    destination.with_suffix('.live.json').write_text(json.dumps(report,indent=2))
    return report
