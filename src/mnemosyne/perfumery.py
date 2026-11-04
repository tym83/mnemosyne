"""A formula from the material of a window.

The story of a window is told by evaporation: the first act of the skeleton
speaks in the opening of the scent, the last one in its drydown. Each
function of the skeleton chooses an accord from the atlas; a search over
proportions then looks for the formula whose headspace, checked at a few
moments after application, is dominated by the right accord at the right
time. Everything is a choice inside the atlas: no material outside the
catalogue, no proportion above its bound, the sum is exactly 100 %.

The search writes its own notebook: the brief, the accords considered,
the trials that lost and why.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import yaml

ATLAS = Path(__file__).resolve().parents[2] / "atlas" / "perfumery"
CHECKPOINTS_H = [0.25, 1.0, 3.0, 6.0, 10.0]
STEP = 0.1  # percent


def atlas():
    mats = {m["id"]: m for m in yaml.safe_load((ATLAS / "materials.yaml").read_text())}
    accords = yaml.safe_load((ATLAS / "accords.yaml").read_text())
    return mats, accords


def brief(mat: dict, rng) -> dict:
    """Which accords tell this window, in the order the scent unfolds."""
    _, accords = atlas()
    order = []
    for act in mat["skeleton"]:
        for f in act["functions"]:
            fn = f["function"]
            if fn in accords and fn not in [o["function"] for o in order]:
                order.append({"function": fn, "weight": float(act.get("weight") or 0.5)})
    if len(order) > 5:  # a scent carries five ideas at most
        keep = sorted(order, key=lambda o: -o["weight"])[:5]
        order = [o for o in order if o in keep]
    label = mat["window"]
    if label.startswith(("quarter:", "year:")):
        q = label.split("-Q")[-1] if "-Q" in label else "4"
        order.append({"function": f"season-Q{q}", "weight": 0.5})
    mats, _ = atlas()
    chosen = []
    n = len(order)
    for i, o in enumerate(order):
        options = accords[o["function"]]
        # Prefer the accord whose materials evaporate when this act should speak.
        target = math.log10(0.4) + (i / max(1, n - 1)) * (math.log10(60) - math.log10(0.4))
        fit = [-abs(np.average([math.log10(mats[m]["tau_h"]) for m in x["parts"]],
                               weights=list(x["parts"].values())) - target) + rng.normal(0, 0.15) for x in options]
        pick = options[int(np.argmax(fit))]
        chosen.append({**o, "accord": pick["name"], "parts": pick["parts"],
                       "considered": [x["name"] for x in options]})
    return {"window": label, "arc": chosen}


def headspace(x: dict, mats: dict, t: float) -> dict:
    """Share of each material in what the nose meets t hours after application."""
    # A material leaves the skin at a rate proportional to what is left of it:
    # x(t) = x0·e^(−t/τ), so what reaches the nose is x0/τ·e^(−t/τ).
    w = {k: v * mats[k].get("odor", 1) / mats[k]["tau_h"] * math.exp(-t / mats[k]["tau_h"]) for k, v in x.items()}
    s = sum(w.values()) or 1
    return {k: v / s for k, v in w.items()}


def score(x: dict, arc: list, mats: dict) -> tuple[float, list]:
    """How well the evaporation tells the story: at checkpoint k the accord of
    the k-th act (stretched over the checkpoints) should lead."""
    n = len(arc)
    times = list(np.geomspace(0.2, 14, max(len(CHECKPOINTS_H), n)))
    owners = {}
    for a in arc:
        for m in a["parts"]:
            owners[m] = owners.get(m, 0) + 1
    detail, total = [], 0.0
    for ci, t in enumerate(times):
        want = min(n - 1, int(ci * n / len(times)))
        hs = headspace(x, mats, t)
        # A material shared by several accords speaks for each of them in part.
        share = [sum(hs.get(m, 0) / owners[m] for m in a["parts"]) for a in arc]
        lead = int(np.argmax(share))
        total += share[want] - 0.5 * max(0, max(share) - share[want])
        detail.append({"hours": round(float(t), 2), "wanted": arc[want]["function"], "leading": arc[lead]["function"],
                       "shares": {a["function"]: round(s, 3) for a, s in zip(arc, share)}})
    return total / len(times), detail


def candidate(arc: list, mats: dict, rng) -> dict:
    x = {}
    n = len(arc)
    for i, a in enumerate(arc):
        # Early acts are pushed towards volatile materials, late ones towards fixatives.
        pos = i / max(1, n - 1)
        for m, parts in a["parts"].items():
            tau = mats[m]["tau_h"]
            fit = math.exp(-abs(math.log10(tau) - (math.log10(0.4) + pos * (math.log10(60) - math.log10(0.4)))))
            x[m] = x.get(m, 0) + parts * (0.3 + fit) * rng.gamma(2.0, 0.5) * (0.5 + a["weight"])
    # A carrier of transparent woods and musks holds the composition together.
    for m, base in (("iso-e", 3), ("ethylene-brassylate", 4)):
        x[m] = x.get(m, 0) + base * rng.gamma(2.0, 0.5)
    return normalise(x, mats)


def normalise(x: dict, mats: dict) -> dict:
    """Scale to 100 %, respect the bounds (water-filling: materials at their
    bound stay there, the rest share what is left), round to the dosing step."""
    x = {k: v for k, v in x.items() if v > 0}
    if sum(mats[k]["max_pct"] for k in x) < 100:
        # Too few materials to fill a concentrate: the rest is solvent.
        x["dpg"] = x.get("dpg", 0) + 1.0
    fixed: dict = {}
    free = dict(x)
    while True:
        left = 100 - sum(fixed.values())
        s = sum(free.values())
        if not free or s <= 0:
            free = {"dpg": 1.0}
            s = 1.0
        scaled = {k: v * left / s for k, v in free.items()}
        over = [k for k, v in scaled.items() if v > mats[k]["max_pct"]]
        if not over:
            break
        for k in over:
            fixed[k] = mats[k]["max_pct"]
            free.pop(k)
    x = {**fixed, **scaled}
    q = {k: round(v / STEP) * STEP for k, v in x.items() if v >= STEP}
    diff = round(100 - sum(q.values()), 1)
    if diff:
        room = [k for k in q if 0 <= q[k] + diff <= mats[k]["max_pct"]]
        k = max(room, key=lambda k: q[k]) if room else "dpg"
        q[k] = round(q.get(k, 0) + diff, 1)
    return dict(sorted(q.items(), key=lambda kv: -kv[1]))


def valid(x: dict, mats: dict) -> bool:
    return abs(sum(x.values()) - 100) < 1e-6 and all(0 < v <= mats[m]["max_pct"] + 1e-9 for m, v in x.items())


def compose(mat: dict, seed: int, trials: int = 4000) -> dict:
    mats, _ = atlas()
    rng = np.random.default_rng(seed)
    b = brief(mat, rng)
    best, notebook = None, []
    for k in range(trials):
        x = candidate(b["arc"], mats, rng)
        if not valid(x, mats):
            continue
        sc, det = score(x, b["arc"], mats)
        if best is None or sc > best[0]:
            if best is not None:
                notebook.append({"trial": k, "score": round(best[0], 4), "fate": "surpassed",
                                 "formula": best[1]})
            best = (sc, x, det)
    # Then polish the winner by small moves, as a perfumer adjusts a trial.
    sc, x, det = best
    for k in range(trials):
        y = dict(x)
        m = list(y)[int(rng.integers(0, len(y)))]
        y[m] = max(STEP, y[m] * float(np.exp(rng.normal(0, 0.35))))
        y = normalise(y, mats)
        if not valid(y, mats):
            continue
        s2, d2 = score(y, b["arc"], mats)
        if s2 > sc:
            notebook.append({"trial": trials + k, "score": round(sc, 4), "fate": "adjusted", "formula": x})
            sc, x, det = s2, y, d2
    tiers = {"top": 0.0, "heart": 0.0, "base": 0.0}
    for m, v in x.items():
        if not mats[m].get("odor", 1):
            continue
        tau = mats[m]["tau_h"]
        tiers["top" if tau < 2 else "heart" if tau < 15 else "base"] += v
    assert valid(x, mats)
    return {
        "window": mat["window"], "cluster": mat["cluster"], "seed": seed,
        "brief": b, "score": round(sc, 4), "unfolding": det,
        "formula": [{"material": m, "name": mats[m]["name"], "percent": v, "family": mats[m]["family"]} for m, v in x.items()],
        "pyramid": {k: round(v, 1) for k, v in tiers.items()},
        "notebook": {"trials": trials, "surpassed": notebook[-12:]},
    }


def passport(f: dict) -> str:
    lines = [f"# Formula — {f['cluster']}, {f['window']}", "",
             "Concentrate, mass percent. Dilute to 18 % in perfumer's alcohol.", "",
             "| Material | % | Family |", "|---|---:|---|"]
    lines += [f"| {r['name']} | {r['percent']:.1f} | {r['family']} |" for r in f["formula"]]
    lines += ["", f"Pyramid: top {f['pyramid']['top']} %, heart {f['pyramid']['heart']} %, base {f['pyramid']['base']} %.", "",
              "How it unfolds:", ""]
    for d in f["unfolding"]:
        lines.append(f"- after {d['hours']} h: wanted «{d['wanted']}», leads «{d['leading']}»")
    return "\n".join(lines) + "\n"


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Compose formulas for windows.")
    ap.add_argument("materials", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/works/perfumery"))
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for p in a.materials:
        mat = json.loads(p.read_text())
        # Each window has its own seed: the same skeleton in another window
        # must not give the same scent.
        seed = a.seed + int.from_bytes(hashlib.sha256((mat["cluster"] + mat["window"]).encode()).digest()[:4], "big")
        f = compose(mat, seed)
        stem = f"{mat['cluster']}_{mat['window'].replace(':', '_')}"
        (a.out / f"{stem}.json").write_text(json.dumps(f, ensure_ascii=False, indent=1))
        (a.out / f"{stem}.md").write_text(passport(f))
        print(stem, f["score"], [x["accord"] for x in f["brief"]["arc"]], f["pyramid"], len(f["formula"]), "materials")


if __name__ == "__main__":
    main()
