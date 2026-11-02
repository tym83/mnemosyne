"""The mood of an artist: what a stretch of life leaves behind.

No event reaches a work directly. The life and the state of a cluster are
dissolved into a handful of qualities of experience — how turbulent or
even it was, how crowded or lonely, whether it knew loss, renewal, scars,
how open or closed its body is, how old it is — with a memory that fades:
recent months weigh more than old ones, but nothing is forgotten
entirely. The mood is what an artist brings to a work; the work itself
is born from a concept, by the logic of its art.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

STEP_MIN = 5


def _decay_weights(n: int, half_life_steps: float) -> np.ndarray:
    w = 0.5 ** ((n - 1 - np.arange(n)) / half_life_steps)
    return w / w.sum()


def mood(scenarios: Path, cluster: str, until: datetime, half_life_days: float = 60) -> dict:
    facts = json.loads((scenarios / cluster / "facts.json").read_text())
    sig = dict(np.load(scenarios / cluster / "signals.npz"))
    start = datetime.fromisoformat(facts["start"])
    n = max(1, min(len(sig["load"]), int((until - start).total_seconds() // (STEP_MIN * 60))))
    w = _decay_weights(n, half_life_days * 288)
    load, unready, lat = sig["load"][:n].astype(float), sig["unready"][:n].astype(float), sig["latency_ms"][:n].astype(float)
    # Qualities of experience, each in [0, 1], measured against the
    # cluster's own usual week: a bank's empty nights are not a storm.
    week = 7 * 288
    idx = np.arange(n) % week
    base = np.array([np.median(load[idx == k]) if (idx == k).any() else 1.0 for k in range(week)])
    ratio = load / np.maximum(base[idx], 1e-6)
    lat_base = np.array([np.median(lat[idx == k]) if (idx == k).any() else 1.0 for k in range(week)])
    lat_ratio = lat / np.maximum(lat_base[idx], 1e-6)
    logmap = lambda frac, lo, span: float(np.clip((np.log10(max(frac, 1e-7)) - lo) / span, 0, 1))
    # Ranges are set so four very different clusters spread over [0, 1].
    turbulence = logmap((w * (unready > 0.05)).sum(), -4.0, 2.2)
    volatility = float(np.clip((np.sqrt((w * (ratio - 1) ** 2).sum()) - 0.3) / 0.6, 0, 1))
    crowding = logmap((w * (ratio > 2)).sum(), -2.5, 1.5)
    strain = logmap((w * (lat_ratio > 2)).sum(), -4.0, 2.5)
    incidents = [x for x in facts["incidents"] if datetime.fromisoformat(x["start"]) < until]
    ages = np.array([(until - datetime.fromisoformat(x["start"])).days for x in incidents] or [10**6])
    sev = np.array([x["severity"] for x in incidents] or [0.0])
    scars = float(np.clip((sev * 0.5 ** (ages / half_life_days)).sum() / 3, 0, 1))
    tenants = facts["tenants"]
    gone = [t for t in tenants if t["died"] and datetime.fromisoformat(t["died"]) < until]
    born = [t for t in tenants if datetime.fromisoformat(t["born"]) < until]
    loss = float(np.clip(len(gone) / max(1, len(born)) * 1.5, 0, 1))
    renewal = float(np.clip(sum(1 for t in born if (until - datetime.fromisoformat(t["born"])).days < 120) / 6, 0, 1))
    upgraded = datetime.fromisoformat(facts["upgrade"]["at_utc"]) < until
    moved = bool(facts.get("migration")) and datetime.fromisoformat(facts["migration"]["at"]).replace(
        tzinfo=start.tzinfo) < until
    services = facts["services"]
    density = float(np.clip(sum(len(s["deps"]) for s in services) / max(1, len(services)) / 3, 0, 1))
    closed = 0.2
    for line in (scenarios / cluster / "ops.jsonl").open():
        if '"default-deny"' in line and f'"namespace": "{cluster}"' in line:
            closed = 1.0
            break
    age = float(np.clip((until - start).days / 365, 0, 1))
    steadiness = float(np.clip(1 - 0.5 * turbulence - 0.5 * volatility, 0, 1))
    q = {"turbulence": turbulence, "volatility": volatility, "crowding": crowding, "strain": strain,
         "scars": scars, "loss": loss, "renewal": renewal, "steadiness": steadiness, "density": density,
         "closedness": closed, "age": age}
    q = {k: round(v, 3) for k, v in q.items()}
    return {"cluster": cluster, "until": until.isoformat(), "qualities": q,
            "turns": {"new_period": upgraded, "journey": moved}, "words": words(q, upgraded, moved)}


def words(q: dict, upgraded: bool, moved: bool) -> str:
    """The mood in words, for an artist who must never hear the facts."""
    def lvl(x, lo, mid, hi):
        return lo if x < 0.33 else mid if x < 0.66 else hi
    parts = [
        lvl(q["steadiness"], "жизнь была неровной, рваной", "жизнь шла то ровно, то срываясь", "жизнь была ровной, почти неподвижной"),
        lvl(q["crowding"], "было пустынно и тихо", "бывало людно", "было тесно от людей, праздников и толп"),
        lvl(q["scars"], "ран почти не осталось", "остались шрамы", "свежие глубокие шрамы"),
        lvl(q["loss"], "потерь не было", "кто-то ушёл", "многое ушло безвозвратно"),
        lvl(q["renewal"], "нового почти не появлялось", "приходило новое", "всё время приходило новое"),
        lvl(q["closedness"], "двери открыты", "двери полуоткрыты", "двери заперты, порядок строгий"),
        lvl(q["density"], "связей мало, каждый сам по себе", "связей в меру", "всё тесно переплетено"),
        lvl(q["age"], "всё молодо", "уже не молодо", "долгая жизнь позади"),
    ]
    if upgraded:
        parts.append("была смена эпохи, после которой всё стало иначе")
    if moved:
        parts.append("было переселение на новое место")
    return "; ".join(parts) + "."


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["shop", "bank", "ml", "startup"])
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--until", default="2025-12-31T23:00:00+00:00")
    a = ap.parse_args()
    for c in a.clusters:
        m = mood(a.scenarios, c, datetime.fromisoformat(a.until))
        print(c, m["qualities"])
        print("  ", m["words"])


if __name__ == "__main__":
    main()
