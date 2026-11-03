#!/usr/bin/env bash
# Hand a task to Codex and let it work in this repository.
#
#   hack/codex/delegate.sh out/codex/tasks/retry.md
#
# The task file is the whole brief. Codex works in the repository with
# network on (for kubectl and pip), commits on the current branch and ends
# with a report. When the model is at capacity the task is resumed after a
# pause, up to a number of tries.
set -uo pipefail

task=${1:?task file}
name=$(basename "$task" .md)
root=$(cd "$(dirname "$0")/../.." && pwd)
out="$root/out/codex"
mkdir -p "$out"
log="$out/$name.log"
report="$out/$name.report.md"
tries=${TRIES:-12}

opts=(-s workspace-write -c 'approval_policy="never"' -c sandbox_workspace_write.network_access=true
      --add-dir "$HOME/.kube" --add-dir "$HOME/.cache/uv" --skip-git-repo-check -o "$report")
cd "$root" || exit 1
# Sessions are matched by working directory, so `resume --last` finds this
# task and not the artists' short calls, which run in scratch directories.
run() { codex exec "${opts[@]}" "$@" </dev/null >>"$log" 2>&1; }

: >"$report"
echo "=== $(date -u +%FT%TZ) start $task" >>"$log"
run -C "$root" -- "$(cat "$task")"
for i in $(seq 2 "$tries"); do
  if [ -s "$report" ] && ! tail -5 "$log" | grep -q "at capacity"; then
    break
  fi
  echo "=== $(date -u +%FT%TZ) try $i: resuming after a pause" >>"$log"
  sleep $((60 * i))
  run resume --last "Continue the task where you stopped. Check the current state first."
done
echo "=== $(date -u +%FT%TZ) end" >>"$log"
[ -s "$report" ] && cat "$report"
