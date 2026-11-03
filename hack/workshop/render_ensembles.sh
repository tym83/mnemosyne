#!/usr/bin/env bash
# Deterministic orchestration only. No artist/Codex subprocesses.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() {
  kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop -n tenant-scheherazade "$@"
}
run_id="${INSTRUMENTARIUM_RUN:-instrumentarium-v3}"
local_output="${INSTRUMENTARIUM_OUT:-out/works/music/ensembles}"
if [[ ! "$run_id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo 'Invalid INSTRUMENTARIUM_RUN' >&2
  exit 1
fi
kube cp src/scheherazade/music studio-0:/work/src/src/scheherazade/
kube exec studio-0 -- test -x /work/sfizz-build/library/bin/sfizz_render
kube exec studio-0 -- nice -n 19 env PYTHONPATH=/work/src/src \
  /work/venv/bin/python -m scheherazade.music.sample_bank --native /work/samples/instrumentarium
status=0
kube exec studio-0 -- nice -n 19 ionice -c 3 env PYTHONPATH=/work/src/src \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  /work/venv/bin/python -m scheherazade.music.ensemble_demos \
  --out "/work/gen/$run_id" "$@" || status=$?
# Snapshot only complete works, then transfer independently verified 1 MiB chunks.
uv run python hack/workshop/fetch_ensembles.py --run "$run_id" --out "$local_output"
if [ -d "$local_output/schools" ]; then
  uv run python -m scheherazade.music.distinctness "$local_output/schools" \
    --out "$local_output/distinctness.json"
fi
exit "$status"
