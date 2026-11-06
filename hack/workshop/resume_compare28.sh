#!/usr/bin/env bash
# Isolated, deterministic auditions only. No artists or other tenants.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() { kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop -n tenant-scheherazade "$@"; }
kube exec studio-0 -- mkdir -p /work/task28/src /work/tmp /work/models
 tar -C src -cf - mnemosyne | kube exec -i studio-0 -- tar -C /work/task28/src -xf -
for file in compare28 complete_vsco28 download_salamander28 prepare_compare28 measure28 neural_compare28; do
 kube cp "hack/workshop/$file.py" "studio-0:/work/task28/$file.py"
done
step() {
 local id code; id=$(date +%s%N)
 kube exec studio-0 -- sh -c "nohup sh -c 'env TMPDIR=/work/tmp PYTHONPATH=/work/task28/deps:/work/task28/src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=2 /work/venv/bin/python /work/task28/$* > /work/task28/step-$id.log 2>&1; echo \$? > /work/task28/step-$id.exit' </dev/null >/dev/null 2>&1 &"
 code=
 until [ -n "$code" ]; do sleep 30; code=$(kube exec studio-0 -- cat "/work/task28/step-$id.exit" 2>/dev/null || true); done
 if [ "$code" != 0 ]; then kube exec studio-0 -- tail -25 "/work/task28/step-$id.log"; return 1; fi
}
step prepare_compare28.py
for candidate in before sso vsco vpo musescore salamander after-b after-a-b; do step "compare28.py $candidate"; done
step measure28.py
# Neural environment is separately pinned; see compare28-neural-requirements.txt.
if [ "${NEURAL:-0}" = 1 ]; then step neural_compare28.py; fi
