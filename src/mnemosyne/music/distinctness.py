"""Descriptive school-demo distances, not a classifier or an artistic verdict."""
import argparse
import itertools
import json
from pathlib import Path
import numpy as np
from .schools.performance import sounding_events


def features(score,bpm):
    pitches=[];lengths=[];velocities=[];intervals=[];timbres={};attacks=0
    from music21.instrument import UnpitchedPercussion
    for part in score.parts:
        instrument=part.recurse().getElementsByClass('Instrument').first()
        name=instrument.instrumentName
        unpitched=isinstance(instrument,UnpitchedPercussion)
        events=list(sounding_events(part))
        last=None
        for at,length,ps,velocity,glide in events:
            attacks+=1
            if not unpitched:pitches.extend(ps)
            lengths.append(length*60/bpm);velocities.append(velocity)
            timbres[name]=timbres.get(name,0)+length*len(ps)
            for p in (() if unpitched else ps):
                if last is not None:
                    ic=round(abs(p-last))%12;intervals.append(min(ic,12-ic))
                last=p
    if not attacks:raise ValueError('Cannot compare an empty score')
    seconds=float(score.highestTime)*60/bpm
    hist=np.bincount(intervals,minlength=7).astype(float);hist/=max(1,hist.sum())
    dur=np.histogram(lengths,bins=[0,.25,.5,1,2,4,8,float('inf')])[0].astype(float);dur/=max(1,dur.sum())
    dyn=np.histogram(velocities,bins=[0,32,48,64,80,96,112,128])[0].astype(float);dyn/=max(1,dyn.sum())
    weight=sum(timbres.values())
    return {'register':[min(pitches),max(pitches),float(np.std(pitches))] if pitches else [0,0,0],
            'density':attacks/max(seconds,1e-9),'interval_classes':hist.tolist(),
            'durations':dur.tolist(),'dynamics':dyn.tolist(),
            'timbres':{k:v/weight for k,v in sorted(timbres.items())},'seconds':seconds}


def compare(items):
    names=sorted(items);timbres=sorted({k for f in items.values() for k in f['timbres']})
    vectors={name:[np.array(f['register'])/127,np.array([f['density']/(1+f['density'])]),
        np.array(f['interval_classes']),np.array(f['durations']),np.array(f['dynamics']),
        np.array([f['timbres'].get(k,0) for k in timbres])] for name,f in items.items()}
    pairs=[]
    for a,b in itertools.combinations(names,2):
        distances=[float(np.linalg.norm(x-y)/max(1,np.sqrt(len(x)))) for x,y in zip(vectors[a],vectors[b])]
        pairs.append({'a':a,'b':b,'distance':float(np.mean(distances)),
                      'by_feature':dict(zip(('register','density','intervals','durations','dynamics','timbres'),distances))})
    pairs.sort(key=lambda p:(p['distance'],p['a'],p['b']))
    return {'method':'Mean RMS distance of six normalized feature groups; lower is closer. No artistic threshold.',
            'features':items,'closest_pairs':pairs[:10],'identical_pairs':[p for p in pairs if p['distance']<1e-9]}


def main():
    from music21 import converter
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('root',type=Path);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();items={}
    for p in sorted(args.root.glob('*/plan.json')):
        if not (p.parent/'render.json').exists():continue
        plan=json.loads(p.read_text());score=converter.parse(p.parent/'score.musicxml').toSoundingPitch()
        items[p.parent.name]=features(score,plan['tempo'])
    if len(items)<2:raise ValueError('Need at least two completed works')
    report=compare(items);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2))
    print(json.dumps(report['closest_pairs'][:5],indent=2))
    if report['identical_pairs']:raise SystemExit(1)


if __name__=='__main__':main()
