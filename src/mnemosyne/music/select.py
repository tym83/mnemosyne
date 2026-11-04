"""Choosing music: plans for a nocturne and a symphony, and the critics.

The model writes candidates; the plan says what the work must be. A
nocturne of a day is a slow keyboard piece of a few minutes whose own
tension follows the tension of that day and whose opening comes back. A
symphony of a year has four movements of contrasting character; each
movement follows its part of the year, and the movements are chosen so
their openings are related, which is what makes four pieces one cycle.

Every candidate is scored and kept: the winners become the opus, the
rest are the sketches in its notebook.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import analyze

# Teachers by temperament of the cluster: an eventful life speaks through
# the Romantics, an orderly one through the Classical masters.
SYMPHONY_TEACHERS = {
    "eventful": ["Romantic|Tchaikovsky, Pyotr|Orchestral", "Romantic|Dvorak, Antonin|Orchestral"],
    "orderly": ["Classical|Haydn, Joseph|Orchestral", "Classical|Mozart, Wolfgang Amadeus|Orchestral"],
}
NOCTURNE_TEACHER = "Romantic|Chopin, Frederic|Keyboard"

MOVEMENTS = [
    {"n": 1, "name": "Allegro", "part": (0.0, 0.35), "slow": False, "triple": None, "seconds": (360, 900)},
    {"n": 2, "name": "Adagio", "part": (0.35, 0.6), "slow": True, "triple": None, "seconds": (300, 900)},
    {"n": 3, "name": "Scherzo", "part": (0.6, 0.8), "slow": False, "triple": True, "seconds": (180, 600)},
    {"n": 4, "name": "Finale", "part": (0.8, 1.0), "slow": False, "triple": None, "seconds": (300, 900)},
]


def temperament(material: dict) -> str:
    trouble = sum(1 for a in material["skeleton"] for f in a["functions"] if f["function"] in ("trouble", "crowd", "journey"))
    return "eventful" if trouble >= 4 else "orderly"


def _fit(curve_target: list[float], f: dict) -> float:
    t = np.array(curve_target, dtype=float)
    if t.std() < 1e-6:
        # A quiet stretch: reward a piece that stays even.
        p = analyze.tension_proxy(f)
        return float(1 / (1 + p.std()))
    p = analyze.tension_proxy(f, len(t))
    return float(np.corrcoef(t, p)[0, 1])


def _range_ok(f: dict) -> float:
    notes = sum(r["notes"] for r in f["ranges"]) or 1
    return 1 - sum(r["out_of_range"] for r in f["ranges"]) / notes


def score_nocturne(f: dict, material: dict) -> dict:
    sec = f["seconds"] or f["bars"] * 3
    length = 1.0 if 150 <= sec <= 420 else 0.5 if 90 <= sec <= 600 else 0.0
    slow = 1.0 if (f["bpm"] or 80) <= 80 else 0.4
    fit = _fit(material["tension"], f)
    total = 0.35 * fit + 0.25 * f["reprise"] + 0.15 * length + 0.1 * slow + 0.15 * _range_ok(f)
    return {"total": round(total, 4), "fit": round(fit, 3), "reprise": f["reprise"], "length": length, "slow": slow}


def score_movement(f: dict, mv: dict, curve: list[float], opening: list[int] | None) -> dict:
    sec = f["seconds"] or f["bars"] * 2
    lo, hi = mv["seconds"]
    length = 1.0 if lo <= sec <= hi else 0.5 if lo / 2 <= sec <= hi * 1.5 else 0.0
    bpm = f["bpm"] or 100
    tempo = 1.0 if (bpm <= 76) == mv["slow"] else 0.2
    triple = 1.0
    if mv["triple"]:
        triple = 1.0 if f["time_signature"] in ("3/4", "3/8", "6/8") else 0.1
    fit = _fit(curve, f)
    unity = analyze.motif_similarity(opening, f["motif"]) if opening else 0.5
    parts = min(1.0, f["parts"] / 8)
    total = 0.25 * fit + 0.2 * unity + 0.15 * length + 0.15 * tempo + 0.1 * triple + 0.1 * parts + 0.05 * _range_ok(f)
    return {"total": round(total, 4), "fit": round(fit, 3), "unity": round(unity, 3), "length": length,
            "tempo": tempo, "triple": triple, "parts": f["parts"]}


def _analyse_dir(d: Path) -> list[dict]:
    out = []
    for abc in sorted(d.glob("*.abc")):
        try:
            f = analyze.features(analyze.to_musicxml(abc))
        except Exception as e:  # a broken candidate is a sketch that failed
            out.append({"file": abc.name, "error": str(e)[:200]})
            continue
        out.append({"file": abc.name, "features": f})
    return out


def choose_nocturne(cands_dir: Path, material: dict) -> dict:
    cands = _analyse_dir(cands_dir)
    for c in cands:
        if "features" in c:
            c["score"] = score_nocturne(c["features"], material)
    ok = [c for c in cands if "score" in c]
    ok.sort(key=lambda c: -c["score"]["total"])
    return {"plan": {"form": "ABA'", "teacher": NOCTURNE_TEACHER}, "chosen": ok[0]["file"] if ok else None,
            "candidates": cands}


def choose_symphony(cands: dict[int, Path], material: dict) -> dict:
    """cands: movement number → directory of candidates for that movement."""
    curve = material["tension"]
    n = len(curve)
    chosen, opening, notebook = {}, None, {}
    for mv in MOVEMENTS:
        a, b = int(mv["part"][0] * n), int(mv["part"][1] * n)
        seg = curve[a:max(b, a + 2)]
        cs = _analyse_dir(cands[mv["n"]])
        for c in cs:
            if "features" in c:
                c["score"] = score_movement(c["features"], mv, seg, opening)
        ok = sorted([c for c in cs if "score" in c], key=lambda c: -c["score"]["total"])
        notebook[mv["n"]] = cs
        if ok:
            chosen[mv["n"]] = ok[0]["file"]
            if opening is None:
                # The first movement's opening is the motto of the cycle.
                opening = ok[0]["features"]["motif"]
    return {"plan": {"movements": MOVEMENTS, "temperament": temperament(material)},
            "chosen": chosen, "motto": opening, "candidates": notebook}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["nocturne", "symphony"])
    ap.add_argument("--material", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True,
                    help="nocturne: a directory; symphony: a directory with mv1..mv4")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    mat = json.loads(a.material.read_text())
    if a.kind == "nocturne":
        r = choose_nocturne(a.candidates, mat)
    else:
        r = choose_symphony({i: a.candidates / f"mv{i}" for i in range(1, 5)}, mat)
    a.out.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps({"chosen": r["chosen"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
