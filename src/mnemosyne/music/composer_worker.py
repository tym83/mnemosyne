"""Music-only studio worker. Never invokes Writer or reads the recipient key."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from . import analyze
from .render import render_score, notation_score, run, FONT


def execute(request, out):
    out.mkdir(parents=True, exist_ok=False)
    action = request['action']
    # Schools born in the atelier travel with the request; admission is re-checked here.
    from .school_birth import register
    for name, born in request.get('born_schools', {}).items():
        register(name, born['source'], born.get('plan'))
    if action == 'notagen':
        prompt = request['prompt'].split('|')
        if len(prompt) != 3 or not all(prompt):
            raise ValueError('NotaGen requires period|composer|instrumentation')
        subprocess.run([os.environ.get('MNEMO_NOTAGEN_PYTHON', sys.executable), '-m', 'mnemosyne.music.notagen_batch',
            '--prompt', request['prompt'], '--count', '2', '--procs', '1', '--threads', '4',
            '--out', str(out/'candidates')], check=True)
        from .select import _analyse_dir
        from .render import render
        candidates = _analyse_dir(out/'candidates')
        if not any('features' in c for c in candidates):
            raise ValueError('NotaGen produced no readable candidates')
        rendered = out/'rendered'
        (rendered/'.drafts').mkdir(parents=True)
        for c in candidates:
            if 'features' in c:
                source = out/'candidates'/c['file']
                render(source, rendered, FONT, FONT, notation_only=True)
                from music21 import converter
                import hashlib
                score = converter.parse(analyze.to_musicxml(source)).toSoundingPitch()
                notes = list(score.parts[0].flatten().notes)[:8]
                c['material'] = {'pitches': [n.pitches[-1].ps for n in notes],
                    'durations': [float(n.quarterLength) for n in notes],
                    'source': {'kind': 'notagen', 'chosen': c['file'],
                               'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                               'source_abc': source.read_text()}}
                c['score'] = 'rendered/' + source.stem + '.xml'
                run(['pdftoppm', '-f', '1', '-l', '1', '-scale-to', '1800', '-png', '-singlefile',
                     rendered/(source.stem+'.pdf'), out/source.stem], out/'images.log')
                c['image'] = source.stem+'.png'
        return {'candidates': candidates, 'prompt': prompt}
    plan = request['plan']
    if request.get('form') == 'symphony':
        from .symphony import validate
        validate(plan, study=True)
    bank = Path(os.environ.get('MNEMO_NATIVE_BANK', '/work/samples/instrumentarium'))
    if request.get('form') == 'symphony':
        from .symphony import movement, join_scores, write_score
        from .orchestra_render import render_orchestra
        scores = []
        for i in range(len(plan['movements'])):
            dest = out/f'mv{i}'
            if action == 'woven':
                from ..weave.schools import performance_score
                item = request['movements'][i]
                source = out/f'woven-mv{i}.musicxml'
                source.write_text(item['xml'])
                score = performance_score(source)
                op, assignment = item['plan'], item['assignment']
                render_orchestra(score, op, assignment, dest, bank, compact=True)
            else:
                score, op, assignment, development = movement(plan, i)
                notation_score(score, op, dest, assignment)
                (dest/'development.json').write_text(json.dumps(development, indent=2))
            scores.append(score)
        score = join_scores(scores, plan['title'])
        write_score(score, out/'score.musicxml')
        from .orchestra_render import engravable
        run(['musicxml2ly', '-o', out/'score.ly', engravable(out/'score.musicxml')], out/'notation.log')
        subprocess.run(['pdfunite', *[str(out/f'mv{i}/score.pdf') for i in range(len(scores))],
                        str(out/'score.pdf')], check=True)
        if action == 'woven':
            args = [x for i in range(len(scores)) for x in ('-i', str(out/f'mv{i}/score.flac'))]
            run(['ffmpeg', '-nostdin', '-v', 'error', *args, '-filter_complex',
                 f'concat=n={len(scores)}:v=0:a=1', '-c:a', 'flac', '-sample_fmt', 's32',
                 out/'score.flac'], out/'render.log')
            run(['ffmpeg', '-nostdin', '-v', 'error', '-i', out/'score.flac',
                 '-codec:a', 'libmp3lame', '-q:a', '2', out/'score.mp3'], out/'render.log')
        dest = out
    else:
        dest = out/'rendered'
        if action == 'woven':
            from ..weave.schools import performance_score
            (out/'woven.musicxml').write_text(request['xml'])
            score = performance_score(out/'woven.musicxml')
            if plan.get('audio_profile') == 'native_sfz':
                from .orchestra_render import render_orchestra
                if not request.get('assignment'):
                    raise ValueError('woven native score requires its retained original orchestration')
                render_orchestra(score, plan, request['assignment'], dest, bank, compact=True)
            else:
                if plan.get('hall_profile') != 'openair_jack_lyons':
                    bank = Path(os.environ.get('MNEMO_SF2_BANK', '/work/samples/vsco-schools/vsco-schools.sf2'))
                render_score(score, plan, dest, bank, compact=True)
        else:
            from .schools import SCHOOLS
            score = SCHOOLS[plan['school']].compose(plan, plan['seed'])
            notation_score(score, plan, dest)
    # Deliberately sample beginning, middle, ending; all score pages remain in PDF.
    probe = subprocess.check_output(['pdfinfo', str(dest/'score.pdf')], text=True)
    pages = int(next(line.split(':')[1] for line in probe.splitlines() if line.startswith('Pages:')))
    images = []
    for page in sorted({1, (pages+1)//2, pages}):
        base = out/f'page-{page}'
        run(['pdftoppm', '-f', page, '-l', page, '-scale-to', '1800', '-png', '-singlefile',
             dest/'score.pdf', base], out/'images.log')
        images.append(base.with_suffix('.png').name)
    carriers = ([{'score': f'mv{i}/score.musicxml', 'movement_index': i} for i in range(len(plan['movements']))]
                if request.get('form') == 'symphony' and action != 'woven' else [])
    return {'carriers': carriers, 'score': str((dest/'score.musicxml').relative_to(out)),
            'images': images, 'analysis': analyze.features(dest/'score.musicxml')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    existed = args.out.exists()
    try:
        result = execute(json.loads(args.request.read_text()), args.out)
    except Exception:
        # Also retain stderr remotely if kubectl's connection is interrupted.
        # execute refuses existing destinations; never overwrite a prior result.
        if not existed and args.out.is_dir() and not (args.out/'stderr.log').exists():
            (args.out/'stderr.log').write_text(traceback.format_exc())
        raise
    (args.out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
