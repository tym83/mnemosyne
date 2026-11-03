#!/usr/bin/env bash
# Run Codex tasks one after another, skipping tasks that already have a
# report; waits while another delegated task is running.
#   hack/codex/queue.sh 04b-weave-nocturne 14-orchestra-and-instruments …
cd "$(dirname "$0")/../.." || exit 1
for t in "$@"; do
  while pgrep -f "hack/codex/delegate.sh" >/dev/null; do sleep 60; done
  [ -s "out/codex/$t.report.md" ] && continue
  hack/codex/delegate.sh "out/codex/tasks/$t.md" >/dev/null
done
