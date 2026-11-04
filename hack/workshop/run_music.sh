#!/bin/sh
# Inside a studio pod: candidates for one work.
#   sh run_music.sh nocturne shop      -> /work/gen/shop/nocturne
#   sh run_music.sh symphony shop 1    -> /work/gen/shop/symphony/mv1
set -e
. /work/venv/bin/activate
cd /work/src
test -e /work/src/src/mnemosyne || ln -s scheherazade /work/src/src/mnemosyne
export PYTHONPATH=/work/src/src${PYTHONPATH:+:$PYTHONPATH}
KIND=$1 CLUSTER=$2 MV=$3
case "$KIND" in
  nocturne) PROMPT="Romantic|Chopin, Frederic|Keyboard"; OUT=/work/gen/$CLUSTER/nocturne ;;
  symphony)
    if [ "$CLUSTER" = shop ]; then PROMPT="Romantic|Tchaikovsky, Pyotr|Orchestral"; else PROMPT="Classical|Haydn, Joseph|Orchestral"; fi
    OUT=/work/gen/$CLUSTER/symphony/mv$MV ;;
esac
python -m mnemosyne.music.notagen_batch --prompt "$PROMPT" --count ${COUNT:-3} --procs ${PROCS:-14} --threads ${THREADS:-5} \
  --seed $(echo "$CLUSTER$KIND$MV" | cksum | cut -d' ' -f1) --out $OUT
