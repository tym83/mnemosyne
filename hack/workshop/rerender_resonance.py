"""Run in studio-0 with isolated source checkout; preserve all original works."""
import argparse
import json
from pathlib import Path
import shutil
from music21 import converter
from mnemosyne.music.render import render_score, note_events
from mnemosyne.music.orchestra_render import render_orchestra
from mnemosyne.music.schools import SCHOOLS


def main():
    ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['schools','symphony','native'])
    ap.add_argument('source',type=Path);ap.add_argument('destination',type=Path)
    ap.add_argument('--sf2',type=Path);ap.add_argument('--bank',type=Path,default=Path('/work/samples/instrumentarium'))
    args=ap.parse_args();args.destination.mkdir(parents=True,exist_ok=True)
    if args.kind=='schools':
        for source in sorted(args.source.iterdir()):
            if not (source/'render.json').exists():continue
            dest=args.destination/source.name
            if (dest/'render.json').exists():continue
            plan=json.loads((source/'plan.json').read_text())
            score=SCHOOLS[plan['school']].compose(plan,plan['seed'])
            old=converter.parse(source/'score.musicxml').toSoundingPitch()
            if note_events(score.stripTies())!=note_events(old.stripTies()):raise ValueError(f'Changed notes: {source}')
            render_score(score,plan,dest,args.sf2,compact=True)
    elif args.kind=='native':
        source=args.source
        plan=json.loads((source/'plan.json').read_text());assignment=json.loads((source/'orchestration.json').read_text())
        score=converter.parse(source/'score.musicxml').toSoundingPitch()
        render_orchestra(score,plan,assignment,args.destination,args.bank,compact=True)
    else:
        for name in ['plan.json','weave.json',*[f'mv{i}-development.json' for i in range(1,4)]]:
            if not (args.destination/name).exists():shutil.copy2(args.source/name,args.destination/name)
        for i in range(1,4):
            source=args.source/f'mv{i}';dest=args.destination/f'mv{i}'
            if (dest/'render.json').exists():continue
            plan=json.loads((source/'plan.json').read_text());assignment=json.loads((source/'orchestration.json').read_text())
            score=converter.parse(source/'score.musicxml').toSoundingPitch()
            render_orchestra(score,plan,assignment,dest,args.bank,compact=True)
        from mnemosyne.music.symphony import finalize
        finalize(args.destination)

if __name__=='__main__':main()
