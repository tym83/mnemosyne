#!/usr/bin/env bash
# Build the pinned offline SFZ renderer in the studio, never on the laptop.
set -euo pipefail
kubectl --kubeconfig "$HOME/workshop.txt" --context admin@workshop \
  -n tenant-scheherazade exec -i studio-0 -- sh -s <<'POD'
set -eu
if [ -x /work/sfizz-build/library/bin/sfizz_render ]; then
  /work/sfizz-build/library/bin/sfizz_render --help
  exit 0
fi
apt-get update
apt-get install -y cmake libsndfile1-dev libsamplerate0-dev
curl -L --fail https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3.tar.gz -o /work/sfizz-1.2.3.tar.gz
tar -xzf /work/sfizz-1.2.3.tar.gz -C /work
cmake -S /work/sfizz-1.2.3 -B /work/sfizz-build \
  -DCMAKE_BUILD_TYPE=Release -DSFIZZ_SHARED=ON -DSFIZZ_RENDER=ON \
  -DSFIZZ_JACK=OFF -DSFIZZ_TESTS=OFF
nice -n 19 cmake --build /work/sfizz-build -j2
POD
