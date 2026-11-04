#!/usr/bin/env bash
# Run from the laptop: render finished pieces in both studios, then fetch them.
# Rendering dependencies are installed by prepare.sh inside the pods.
set -euo pipefail
cd "$(dirname "$0")/../.."
kube() {
  kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop \
    -n tenant-scheherazade "$@"
}
for pair in studio-0:nocturne studio-1:symphony; do
  pod=${pair%:*}
  set_name=${pair#*:}
  kube exec "$pod" -- sh -c 'test -e /work/src/src/mnemosyne || ln -s scheherazade /work/src/src/mnemosyne'
  kube cp src/mnemosyne/music/render.py "$pod:/work/src/src/scheherazade/music/render.py"
  kube exec "$pod" -- env PYTHONPATH=/work/src/src /work/venv/bin/python \
    -m mnemosyne.music.render "/work/gen/$set_name"
  mkdir -p "out/works/music/$set_name"
  # Fetch only successfully published pieces, never partial or failed drafts.
  kube exec "$pod" -- nice -n 19 ionice -c 3 sh -c '
    cd "$1"
    set --
    for manifest in *.render.json; do
      [ -f "$manifest" ] || continue
      stem=${manifest%.render.json}
      for ext in abc json xml pdf mp3 mid analysis.json render.json render.log ly engraving.musicxml; do
        set -- "$@" "$stem.$ext"
      done
    done
    if [ "$#" -eq 0 ]; then
      tar -cf - --files-from /dev/null
    else
      tar -cf - "$@"
    fi
  ' sh "/work/gen/$set_name/rendered" | tar -xf - -C "out/works/music/$set_name"
done
