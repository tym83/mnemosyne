"""Draw many pieces from NotaGen-X for one prompt, on CPU, in parallel.

Runs inside a studio pod, next to the NotaGen checkout:

    python -m mnemosyne.music.notagen_batch --prompt "Romantic|Chopin, Frederic|Keyboard" \\
        --count 40 --procs 16 --threads 5 --out /work/gen/nocturne

Every piece is kept, good or bad: the losers are the sketches in the
notebook of the work that is chosen later.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
from multiprocessing import Process
from pathlib import Path

NOTAGEN = Path(os.environ.get("NOTAGEN_DIR", "/work/NotaGen/gradio"))


def worker(idx: int, prompt: list[str], count: int, threads: int, out: Path, seed: int):
    os.environ["OMP_NUM_THREADS"] = str(threads)
    device = os.environ.get("NOTAGEN_DEVICE", "cpu")
    if device not in ("cpu", "cuda"):
        raise ValueError("NOTAGEN_DEVICE must be cpu or cuda")
    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import random

    import torch

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("NotaGen CUDA requested but unavailable")
    torch.set_num_threads(threads)
    random.seed(seed + idx)
    torch.manual_seed(seed + idx)
    os.chdir(NOTAGEN)
    sys.path.insert(0, str(NOTAGEN))
    import config
    if os.environ.get("NOTAGEN_WEIGHTS"):
        config.INFERENCE_WEIGHTS_PATH = os.environ["NOTAGEN_WEIGHTS"]
    with contextlib.redirect_stdout(io.StringIO()):
        from inference import inference_patch  # loads the weights
    for k in range(count):
        t0 = time.time()
        name = f"p{idx:02d}_{k:03d}"
        # The model prints the score as it writes it: keep that stream on
        # disk, so a piece in progress can be watched and is never lost.
        with (out / f"{name}.part").open("w", buffering=1) as part, contextlib.redirect_stdout(part):
            abc = inference_patch(*prompt)
        (out / f"{name}.abc").write_text(abc)
        (out / f"{name}.json").write_text(json.dumps({"prompt": prompt, "seconds": round(time.time() - t0, 1),
                                                       "seed": seed + idx, "index": k}))
        print(f"{name} {time.time() - t0:.0f}s {len(abc)} chars", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True, help="period|composer|instrumentation")
    ap.add_argument("--count", type=int, default=8, help="pieces per process")
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if os.environ.get("MNEMOSYNE_NOTAGEN", "disabled") != "self-hosted":
        ap.error("NotaGen is optional: set MNEMOSYNE_NOTAGEN=self-hosted")
    if min(a.count, a.procs, a.threads) < 1 or len(a.prompt.split("|")) != 3:
        ap.error("positive counts and period|composer|instrumentation required")
    a.out.mkdir(parents=True, exist_ok=True)
    prompt = a.prompt.split("|")
    ps = [Process(target=worker, args=(i, prompt, a.count, a.threads, a.out, a.seed * 1000)) for i in range(a.procs)]
    for p in ps:
        p.start()
    for p in ps:
        p.join()
    if any(p.exitcode != 0 for p in ps):
        raise SystemExit("NotaGen worker failed; partial drafts retained")


if __name__ == "__main__":
    main()
