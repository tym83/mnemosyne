"""Render an accepted composer work to sound in a studio, from its retained scores.

For a work made without sound (--no-sound) or without a backup: the movements'
own MusicXML, plan and orchestration go to the studio's 'woven' render path.

  PYTHONPATH=src .venv/bin/python hack/workshop/render_work.py \
      out/works/composer/<artist>/<night> [--pod studio-1]
"""
import argparse
import json
from pathlib import Path

from mnemosyne.music.composer import Studio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('notebook', type=Path)
    ap.add_argument('--pod', default='studio-1')
    ap.add_argument('--name', default='sound', help='output folder inside the notebook')
    a = ap.parse_args()
    record = json.loads((a.notebook/'notebook.json').read_text())
    final = next(s for s in record['sketches'] if s['id'] == record['final'])
    folder = a.notebook  # carrier and score paths are relative to the notebook
    out = a.notebook/a.name
    if out.exists():
        raise FileExistsError(f'preserved existing render: {out}')
    request = {'action': 'woven', 'plan': final['plan'], 'form': final.get('form', 'school'), 'born_schools': {}}
    if request['form'] == 'symphony':
        request['movements'] = [{'xml': (folder/c['score']).read_text(),
                                 'plan': json.loads((folder/Path(c['score']).parent/'plan.json').read_text()),
                                 'assignment': json.loads((folder/Path(c['score']).parent/'orchestration.json').read_text())}
                                for c in sorted(final['carriers'], key=lambda c: c['movement_index'])]
    else:
        request['xml'] = (folder/final['score']).read_text()
        orchestration = (folder/final['score']).parent/'orchestration.json'
        request['assignment'] = json.loads(orchestration.read_text()) if orchestration.exists() else None
    studio = Studio(a.notebook/'sound-studio', a.pod)
    studio.setup()
    result = studio.run(request, out)
    print(json.dumps({'out': str(out), 'files': sorted(str(p.relative_to(out)) for p in out.rglob('*.mp3'))},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
