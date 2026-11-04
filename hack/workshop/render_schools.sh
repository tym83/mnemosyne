#!/usr/bin/env bash
# Explicit deterministic composers only; no LLM/artist subprocesses.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() {
  kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop \
    -n tenant-scheherazade "$@"
}
kube exec studio-0 -- sh -c 'test -e /work/src/src/mnemosyne || ln -s scheherazade /work/src/src/mnemosyne'
kube cp src/mnemosyne/music/schools studio-0:/work/src/src/scheherazade/music/
for file in render.py sample_bank.py sample_libraries.yaml; do
  kube cp "src/mnemosyne/music/$file" "studio-0:/work/src/src/scheherazade/music/$file"
done
kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
  /work/venv/bin/python -m mnemosyne.music.sample_bank /work/samples/vsco-schools
schools=("$@")
if [ "${#schools[@]}" -eq 0 ]; then
  schools=(tintinnabuli stochastic micropolyphony serial feldman process additive in_c spectral sonorism messiaen ustvolskaya chance tempo_canon aleatoric_counterpoint fibonacci polystylism scelsi drone)
fi
for school in "${schools[@]}"; do
  # Successful works are immutable. Fetch existing renders on a repeated run.
  if ! kube exec studio-0 -- test -s "/work/gen/schools/$school/render.json"; then
    kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
      /work/venv/bin/python -m mnemosyne.music.schools \
      "/work/src/src/scheherazade/music/schools/plans/$school.json" \
      --out "/work/gen/schools/$school"
  fi
  local_dir="out/works/music/schools/$school"
  if [ -e "$local_dir" ]; then
    # Verify existing user files instead of replacing them or nesting copies.
    uv run python - "$local_dir" <<'PYTHON'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
manifest = json.loads((root / 'render.json').read_text())
for name, digest in manifest['artifacts'].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Changed local artifact, preserved: {root / name}')
print(f'Verified existing work: {root}')
PYTHON
  else
    # Publish atomically after a bounded transfer and checksum verification.
    # Large raw WAVs and all render attempts remain in the pod's .drafts.
    mkdir -p out/works/music/schools/.transfers
    transfer=$(mktemp -d "out/works/music/schools/.transfers/$school.XXXXXX")
    transferred=false
    for attempt in 1 2 3; do
      if kube exec studio-0 -- tar -C "/work/gen/schools/$school" \
        --exclude=./.drafts -czf - . > "$transfer/attempt-$attempt.tar.gz"; then
        mkdir "$transfer/files"
        tar -xzf "$transfer/attempt-$attempt.tar.gz" -C "$transfer/files"
        uv run python - "$transfer/files" <<'PYTHON'
import hashlib
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
manifest = json.loads((root / 'render.json').read_text())
for name, digest in manifest['artifacts'].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Transfer checksum mismatch: {root / name}')
print(f'Verified transferred work: {root}')
PYTHON
        mv "$transfer/files" "$local_dir"
        transferred=true
        break
      fi
    done
    if [ "$transferred" != true ]; then
      echo "Transfer failed; retained attempts: $transfer" >&2
      exit 1
    fi
  fi
done
