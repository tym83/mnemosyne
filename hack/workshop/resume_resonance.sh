#!/usr/bin/env bash
# Deterministic rerenders only. Requires studio-0 Ready and space on /work.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() { kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop -n tenant-scheherazade "$@"; }
kube exec studio-0 -- mkdir -p /work/task27${V:+-$V}/src
# Keep the application checkout and old banks/works untouched.
tar -C src -cf - mnemosyne | kube exec -i studio-0 -- tar -C /work/task27${V:+-$V}/src -xf -
kube cp hack/workshop/rerender_resonance.py studio-0:/work/task27${V:+-$V}/rerender.py
# Each step runs detached in the pod and is polled with short calls: a long
# exec stream from the laptop does not survive a flaky link.
studio() {
  local id; id=$(date +%s%N)
  kube exec studio-0 -- sh -c "cd /work/task27${V:+-$V} && nohup sh -c 'nice -n 19 ionice -c 3 env PYTHONPATH=/work/task27${V:+-$V}/src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /work/venv/bin/python $* >step-$id.log 2>&1; echo \$? >step-$id.exit' </dev/null >/dev/null 2>&1 &"
  local code=
  until [ -n "$code" ]; do sleep 30; code=$(kube exec studio-0 -- cat "/work/task27${V:+-$V}/step-$id.exit" 2>/dev/null || true); done
  if [ "$code" != 0 ]; then kube exec studio-0 -- tail -30 "/work/task27${V:+-$V}/step-$id.log"; return 1; fi
}
if ! kube exec studio-0 -- test -s /work/task27${V:+-$V}/bank-v2/manifest.json; then
  studio -m mnemosyne.music.sample_bank /work/samples/vsco-schools --output /work/task27${V:+-$V}/bank-v2
fi
studio /work/task27${V:+-$V}/rerender.py schools /work/gen/schools /work/task27${V:+-$V}/schools-${V:-v2} --sf2 /work/task27${V:+-$V}/bank-v2/vsco-schools.sf2
if ! kube exec studio-0 -- test -s /work/task27${V:+-$V}/native-micropolyphony/render.json; then
  studio /work/task27${V:+-$V}/rerender.py native /work/gen/instrumentarium-v3/schools/micropolyphony /work/task27${V:+-$V}/native-micropolyphony
fi
studio -m mnemosyne.music.resonance_measure /work/gen/schools/tintinnabuli /work/task27${V:+-$V}/schools-${V:-v2}/tintinnabuli --out /work/task27${V:+-$V}/tintinnabuli-measurements.json
studio -m mnemosyne.music.resonance_measure /work/gen/instrumentarium-v3/schools/micropolyphony /work/task27${V:+-$V}/native-micropolyphony --out /work/task27${V:+-$V}/micropolyphony-measurements.json
if ! kube exec studio-0 -- test -s /work/task27${V:+-$V}/symphony-${V:-v2}/work.json; then
  studio /work/task27${V:+-$V}/rerender.py symphony /work/gen/symphony-test-v2 /work/task27${V:+-$V}/symphony-${V:-v2}
fi
# Download public artifacts as checksummed archives with retries; wav stems
# and draft attempts stay in the studio. Refuse overwrites.
uv run --locked python - "${V:-v2}" <<'PYTHON'
import shutil, sys, tempfile
from pathlib import Path
from mnemosyne.music.composer import Studio
v = sys.argv[1]
remote = '/work/task27' + ('' if v == 'v2' else '-' + v)
studio = Studio(Path('out/task27'), 'studio-0')
music = Path('out/works/music')
for name, dest in [(f'schools-{v}', music/f'schools-{v}'), (f'symphony-{v}', music/f'symphony/test-{v}'),
                   ('native-micropolyphony', music/f'native-micropolyphony-{v}')]:
    if dest.exists():
        sys.exit(f'Preserved existing destination: {dest}')
    Path('out/task27/transfers').mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir='out/task27/transfers'))
    studio.fetch(remote, name, tmp)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp/name, dest)
    print('fetched', dest)
PYTHON
mkdir -p out/task27
for name in tintinnabuli-measurements.json micropolyphony-measurements.json; do
  kube cp --retries=10 "studio-0:/work/task27${V:+-$V}/$name" "out/task27/${V:-v2}-$name"
done
