#!/usr/bin/env bash
# Deterministic rerenders only. Requires studio-0 Ready and space on /work.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() { kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop -n tenant-scheherazade "$@"; }
kube exec studio-0 -- mkdir -p /work/task27/src
# Keep the application checkout and old banks/works untouched.
tar -C src -cf - mnemosyne | kube exec -i studio-0 -- tar -C /work/task27/src -xf -
kube cp hack/workshop/rerender_resonance.py studio-0:/work/task27/rerender.py
# Each step runs detached in the pod and is polled with short calls: a long
# exec stream from the laptop does not survive a flaky link.
studio() {
  local id; id=$(date +%s%N)
  kube exec studio-0 -- sh -c "cd /work/task27 && nohup sh -c 'nice -n 19 ionice -c 3 env PYTHONPATH=/work/task27/src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /work/venv/bin/python $* >step-$id.log 2>&1; echo \$? >step-$id.exit' </dev/null >/dev/null 2>&1 &"
  local code=
  until [ -n "$code" ]; do sleep 30; code=$(kube exec studio-0 -- cat "/work/task27/step-$id.exit" 2>/dev/null || true); done
  if [ "$code" != 0 ]; then kube exec studio-0 -- tail -30 "/work/task27/step-$id.log"; return 1; fi
}
if ! kube exec studio-0 -- test -s /work/task27/bank-v2/manifest.json; then
  studio -m mnemosyne.music.sample_bank /work/samples/vsco-schools --output /work/task27/bank-v2
fi
studio /work/task27/rerender.py schools /work/gen/schools /work/task27/schools-v2 --sf2 /work/task27/bank-v2/vsco-schools.sf2
if ! kube exec studio-0 -- test -s /work/task27/native-micropolyphony/render.json; then
  studio /work/task27/rerender.py native /work/gen/instrumentarium-v3/schools/micropolyphony /work/task27/native-micropolyphony
fi
studio -m mnemosyne.music.resonance_measure /work/gen/schools/tintinnabuli /work/task27/schools-v2/tintinnabuli --out /work/task27/tintinnabuli-measurements.json
studio -m mnemosyne.music.resonance_measure /work/gen/instrumentarium-v3/schools/micropolyphony /work/task27/native-micropolyphony --out /work/task27/micropolyphony-measurements.json
if ! kube exec studio-0 -- test -s /work/task27/symphony-v2/work.json; then
  studio /work/task27/rerender.py symphony /work/gen/symphony-test-v2 /work/task27/symphony-v2
fi
# Download only public artifacts, leaving drafts in the studio. Refuse overwrites.
for pair in schools-v2:schools-v2 symphony-v2:symphony/test-v2 native-micropolyphony:native-micropolyphony-v2; do
  remote=${pair%%:*}; local_name=${pair#*:}; dest="out/works/music/$local_name"
  if [ -e "$dest" ]; then echo "Preserved existing destination: $dest" >&2; exit 1; fi
  mkdir -p out/task27/transfers
  transfer=$(mktemp -d out/task27/transfers/render.XXXXXX)
  kube exec studio-0 -- tar -C "/work/task27/$remote" --exclude=.drafts -cf - . > "$transfer/artifacts.tar"
  mkdir "$transfer/files"
  tar -C "$transfer/files" -xf "$transfer/artifacts.tar"
  uv run python - "$transfer/files" <<'PYTHON'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
for path in root.rglob('render.json'):
    manifest=json.loads(path.read_text())
    for name,digest in manifest['artifacts'].items():
        if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=digest:
            raise SystemExit(f'Checksum mismatch: {path.parent/name}')
print(f'Checksums verified: {root}')
PYTHON
  mkdir -p "$(dirname "$dest")"
  mv "$transfer/files" "$dest"
done
mkdir -p out/task27
for name in tintinnabuli-measurements.json micropolyphony-measurements.json; do
  kube cp "studio-0:/work/task27/$name" "out/task27/$name"
done
