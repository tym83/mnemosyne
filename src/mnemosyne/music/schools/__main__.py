"""Compose and render an explicit school plan; run heavy rendering in a pod."""
import argparse
import json
import os
from pathlib import Path
from . import SCHOOLS
from ..render import render_score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--soundfont',type=Path,default=Path('/work/samples/vsco-schools/vsco-schools.sf2'),help='Legacy SF2 profile only')
    parser.add_argument('--sample-bank',type=Path,default=Path('/work/samples/instrumentarium'),help='Native SFZ bank directory')
    args = parser.parse_args()
    os.nice(19)
    plan = json.loads(args.plan.read_text())
    score = SCHOOLS[plan['school']].compose(plan,plan['seed'])
    render_score(score,plan,args.out,args.sample_bank if plan.get('audio_profile')=='native_sfz' else args.soundfont)


if __name__=='__main__':
    main()
