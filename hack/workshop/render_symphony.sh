#!/usr/bin/env bash
# No artist/model calls; all composition, engraving and audio run in studio-0/ws1.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() { kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop -n tenant-scheherazade "$@"; }
run_id="${SYMPHONY_RUN:-symphony-test-v2}"
local_output="${SYMPHONY_OUT:-out/works/music/symphony/test}"
[[ "$run_id" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid run id' >&2; exit 1; }
kube cp src/scheherazade/music studio-0:/work/src/src/scheherazade/
kube cp src/scheherazade/weave studio-0:/work/src/src/scheherazade/
kube exec studio-0 -- /work/venv/bin/python -c 'import cryptography, music21, numpy'
kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 /work/venv/bin/python \
  -m scheherazade.music.symphony \
  --plan /work/src/src/scheherazade/music/plans/symphony-test.json \
  --out "/work/gen/$run_id" "$@"
uv run python hack/workshop/fetch_symphony.py --run "$run_id" --out "$local_output"
