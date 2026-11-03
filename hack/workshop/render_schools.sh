#!/usr/bin/env bash
# Explicit deterministic composers only; no LLM/artist subprocesses.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() {
  kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop \
    -n tenant-scheherazade "$@"
}
kube cp src/scheherazade/music/schools studio-0:/work/src/src/scheherazade/music/
for file in render.py sample_bank.py sample_libraries.yaml; do
  kube cp "src/scheherazade/music/$file" "studio-0:/work/src/src/scheherazade/music/$file"
done
kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
  /work/venv/bin/python -m scheherazade.music.sample_bank /work/samples/vsco-schools
for school in tintinnabuli stochastic micropolyphony serial; do
  # Successful works are immutable. Fetch existing renders on a repeated run.
  if ! kube exec studio-0 -- test -s "/work/gen/schools/$school/render.json"; then
    kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
      /work/venv/bin/python -m scheherazade.music.schools \
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
    mkdir -p "$local_dir"
    kube cp "studio-0:/work/gen/schools/$school/." "$local_dir/"
  fi
done
