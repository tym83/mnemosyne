"""Run deterministic technical listening studies, without invoking any artist/LLM."""
import argparse
import json
from pathlib import Path
from .instrumentarium import ENSEMBLES, REGISTRY, ensemble
from .orchestration import Event, Line, orchestrate, school_lines
from .orchestra_render import render_orchestra
from .schools import SCHOOLS


def demo(name):
    plan={'title':name+' — instrument and articulation study','ensemble':name,
          'duration':40,'tempo':60,'seed':20261103,'audio_profile':'native_sfz',
          'idea':'Technical demonstration of each specified instrument; not an artistic composition.',
          'method':'Five comfortable-register tones, sustained and short attacks; staggered entrances.'}
    lines=[]
    for index,p in enumerate(ensemble(name)):
        spec=p.spec;low,high=spec['comfortable']
        tech='arco' if spec['family']=='strings' else 'sustain'
        zones=spec['samples'].get('key_ranges',{}).get(tech,[])
        available=[key for key in range(low,high+1) if not zones or any(a<=key<=b for a,b in zones)]
        if not available:raise ValueError(f'No comfortable sampled notes for {p.instrument}')
        pitches=[min(available,key=lambda k:abs(k-(low+x))) for x in (0,2,4,7,12)]
        events=[]
        for j in range(8):
            at=j*5+(index%5)*.25
            technique=('arco' if spec['family']=='strings' else 'sustain') if j%2==0 else ('staccato' if 'staccato' in spec['samples']['patches'] else 'sustain' if spec['family']!='strings' else 'pizzicato')
            if spec.get('unpitched'):pitches=[spec['sample_key']]*5
            events.append(Event(at,2 if j%2==0 else .5,(pitches[j%5],),[48,64,80,96][j%4],technique))
        lines.append(Line(p.id,'percussion_layer' if spec.get('unpitched') else 'melody',tuple(events),tuple(spec['range']),.4,None,p.instrument))
    return plan,lines


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['demos','schools','all'],default='all')
    ap.add_argument('--bank',type=Path,default=Path('/work/samples/instrumentarium'))
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--only',nargs='*')
    args=ap.parse_args();failures=[]
    tasks=[]
    if args.mode in ('demos','all'):
        tasks.extend(('ensemble',name) for name in ENSEMBLES)
    if args.mode in ('schools','all'):
        tasks.extend(('school',name) for name in SCHOOLS)
    for kind,name in tasks:
        if args.only and name not in args.only:continue
        destination=args.out/name if kind=='ensemble' else args.out/'schools'/name
        if (destination/'render.json').exists():
            from .native_bank import sha
            old=json.loads((destination/'render.json').read_text())
            for file,digest in old['artifacts'].items():
                if sha(destination/file)!=digest:raise ValueError(f'Changed published artifact: {destination/file}')
            print('Verified existing',destination,flush=True);continue
        try:
            if kind=='ensemble':plan,lines=demo(name)
            else:
                path=Path(__file__).with_name('schools')/'orchestrated_plans'/f'{name}.json'
                plan=json.loads(path.read_text())
                if plan.get('audio_profile') == 'technique_synthesis':
                    from .render import render_score
                    source=SCHOOLS[name].compose(plan,plan['seed'])
                    render_score(source,plan,destination,args.bank)
                    continue
                if plan.get('required_techniques'):
                    raise ValueError('Native sample realization unavailable for required techniques: '+', '.join(plan['required_techniques']))
                source=SCHOOLS[name].compose(plan,plan['seed']);lines=school_lines(source,plan)
            score,assignment=orchestrate(lines,plan)
            render_orchestra(score,plan,assignment,destination,args.bank)
        except Exception as exc:
            failures.append({'kind':kind,'name':name,'error':str(exc)})
            print('FAILED',kind,name,str(exc),flush=True)
    args.out.mkdir(parents=True,exist_ok=True)
    import time
    report=args.out/f'run-{time.time_ns()}.json'
    report.write_text(json.dumps({'failures':failures},indent=2))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
