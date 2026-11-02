"""The material of a window: what the life of a cluster gives a work.

A window is a span of history fixed by the workshop calendar (§59): a day,
an ISO week, a month, a quarter, the year, or an event such as an incident.
For a window the material is

* the tension curve — one number per five minutes, normalised against the
  cluster's own history, so a quiet bank's small spike still counts;
* the skeleton — the functions of the story (trouble, struggle, helper,
  restoration, arrival, loss, silence, a new period, a journey), derived by
  rules from what happened, never by a model;
* the characters — the services, tenants and people who took part.

No technical word reaches a work from here: the skeleton names functions,
the characters are identities the leitmotif registry turns into themes,
colours and archetypes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

STEP = timedelta(minutes=5)
START = datetime(2025, 1, 1, tzinfo=timezone.utc)


@dataclass
class Cluster:
    name: str
    facts: dict
    signals: dict
    ops: list[dict]
    tension: np.ndarray

    @property
    def zone(self):
        return ZoneInfo(self.facts["timezone"])


def load(root: Path, name: str) -> Cluster:
    d = root / name
    facts = json.loads((d / "facts.json").read_text())
    sig = dict(np.load(d / "signals.npz"))
    ops = [json.loads(line) for line in (d / "ops.jsonl").open()]
    return Cluster(name, facts, sig, ops, tension(sig))


def tension(sig: dict) -> np.ndarray:
    """Trouble as one number in [0, 1], relative to the cluster's own normal."""
    unready = sig["unready"]
    warn = sig["warnings"]
    lat = sig["latency_ms"] / np.median(sig["latency_ms"])
    raw = 0.55 * unready / max(np.percentile(unready, 99.9), 0.05) \
        + 0.25 * np.clip((warn - np.median(warn)) / max(np.percentile(warn, 99.9), 1), 0, None) \
        + 0.20 * np.clip((lat - 1) / max(np.percentile(lat, 99.9) - 1, 0.2), 0, None)
    k = np.ones(3) / 3
    return np.clip(np.convolve(raw, k, mode="same"), 0, 1)


def _i(t: datetime) -> int:
    return int((t - START) / STEP)


def _t(i: int) -> datetime:
    return START + i * STEP


def window(c: Cluster, kind: str, spec: str) -> tuple[datetime, datetime, str]:
    """A calendar window in the cluster's local time: day 2025-11-28, week
    2025-W48, month 2025-11, quarter 2025-Q4, year 2025."""
    z = c.zone
    if kind == "day":
        a = datetime.fromisoformat(spec).replace(tzinfo=z)
        b = a + timedelta(days=1)
    elif kind == "week":
        y, w = spec.split("-W")
        a = datetime.combine(date.fromisocalendar(int(y), int(w), 1), datetime.min.time(), z)
        b = a + timedelta(days=7)
    elif kind == "month":
        y, mo = map(int, spec.split("-"))
        a = datetime(y, mo, 1, tzinfo=z)
        b = datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=z)
    elif kind == "quarter":
        y, q = spec.split("-Q")
        mo = (int(q) - 1) * 3 + 1
        a = datetime(int(y), mo, 1, tzinfo=z)
        b = datetime(int(y) + (mo == 10), (mo + 3 - 1) % 12 + 1, 1, tzinfo=z)
    elif kind == "year":
        a = datetime(int(spec), 1, 1, tzinfo=z)
        b = datetime(int(spec) + 1, 1, 1, tzinfo=z)
    else:
        raise ValueError(kind)
    a, b = a.astimezone(timezone.utc), b.astimezone(timezone.utc)
    return max(a, START), min(b, START + len(c.tension) * STEP), f"{kind}:{spec}"


def incident_window(c: Cluster, incident: dict) -> tuple[datetime, datetime, str]:
    """An incident's own window: from the rise of tension to recovery, plus a day."""
    s, e = datetime.fromisoformat(incident["start"]), datetime.fromisoformat(incident["end"])
    i = _i(s)
    while i > 0 and c.tension[i - 1] > 0.1 and _i(s) - i < 36:
        i -= 1
    return _t(i), e + timedelta(days=1), f"incident:{incident['start'][:16]}:{incident['service']}"


def episodes(c: Cluster, a: datetime, b: datetime, threshold: float = 0.35) -> list[dict]:
    """Stretches of trouble: tension above the threshold, gaps under 30 min joined."""
    ia, ib = _i(a), _i(b)
    hot = c.tension[ia:ib] > threshold
    out, i = [], 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j < len(hot) and (hot[j] or (j + 6 < len(hot) and hot[j:j + 6].any())):
            j += 1
        if j - i >= 2:
            out.append({"start": _t(ia + i), "end": _t(ia + j), "peak": float(c.tension[ia + i:ia + j].max())})
        i = j
    return out


def _who(op):
    md = op["object"]["metadata"]
    return md.get("namespace", ""), md["name"], op["object"]["kind"]


def skeleton(c: Cluster, a: datetime, b: datetime, max_acts: int = 9) -> list[dict]:
    """The functions of the window in time order. Long windows keep the most
    significant episodes, so a year has acts, not a list of every hiccup."""
    acts = []
    ops = [o for o in c.ops if a <= datetime.fromisoformat(o["at"]) < b]
    for ep in episodes(c, a, b):
        inside = [o for o in ops if ep["start"] <= datetime.fromisoformat(o["at"]) <= ep["end"] + timedelta(minutes=30)]
        human = [o for o in inside if o["actor_kind"] == "human"]
        inc = next((x for x in c.facts["incidents"]
                    if datetime.fromisoformat(x["start"]) <= ep["end"] and datetime.fromisoformat(x["end"]) >= ep["start"]), None)
        affected = set(inc["affected"]) if inc else set()
        # A helper is a controller that answers the trouble: more replicas of
        # an affected service, or a new node.
        helpers = [o for o in inside if o["actor_kind"] == "controller" and (
            (o["object"]["kind"] == "Node" and o["op"] == "create") or
            (o["object"]["kind"] == "Deployment" and o["object"]["metadata"]["name"] in affected))]
        act = [{"function": "trouble", "at": ep["start"].isoformat(), "weight": round(ep["peak"], 3),
                "who": inc["service"] if inc else None, "affected": inc["affected"] if inc else [],
                "cause": inc["cause"] if inc else None}]
        if human:
            act.append({"function": "struggle", "at": human[0]["at"], "weight": len(human),
                        "who": human[0]["actor"], "deeds": sorted({o["reason"] for o in human if o["reason"]})})
        if helpers:
            act.append({"function": "helper", "at": helpers[0]["at"], "weight": len(helpers),
                        "who": helpers[0]["actor"]})
        if inc and any("rollback" in o["reason"] for o in human):
            act.append({"function": "return-of-the-old", "at": next(o["at"] for o in human if "rollback" in o["reason"]),
                        "weight": 1, "who": inc["service"]})
        act.append({"function": "restoration", "at": ep["end"].isoformat(), "weight": round(ep["peak"], 3)})
        acts.append({"kind": "episode", "at": ep["start"].isoformat(), "weight": ep["peak"], "functions": act})
    for o in ops:
        ns, name, kind = _who(o)
        if kind == "Namespace" and o["actor_kind"] == "human":
            f = "arrival" if o["op"] == "create" else "loss"
            acts.append({"kind": f, "at": o["at"], "weight": 0.6 if f == "loss" else 0.4,
                         "functions": [{"function": f, "at": o["at"], "who": name}]})
    up = c.facts["upgrade"]
    if a <= datetime.fromisoformat(up["at_utc"]) < b:
        acts.append({"kind": "new-period", "at": up["at_utc"], "weight": 0.7,
                     "functions": [{"function": "new-period", "at": up["at_utc"], "from": up["from"], "to": up["to"]}]})
    mig = c.facts.get("migration")
    if mig:
        at = datetime.fromisoformat(mig["at"]).replace(tzinfo=c.zone).astimezone(timezone.utc)
        if a <= at < b:
            acts.append({"kind": "journey", "at": at.isoformat(), "weight": 0.8,
                         "functions": [{"function": "journey", "at": at.isoformat(), "from": mig["from"], "to": mig["to"]}]})
    acts += feasts(c, a, b) + fasts(c, a, b)
    acts.sort(key=lambda x: x["at"])
    if len(acts) > max_acts:
        # Keep every kind of act that happened, then fill with the heaviest:
        # a year is a drama, not a list of its worst nights.
        chosen, kinds = [], {}
        for x in sorted(acts, key=lambda x: -x["weight"]):
            if x["kind"] not in kinds:
                kinds[x["kind"]] = 1
                chosen.append(x)
        for x in sorted(acts, key=lambda x: -x["weight"]):
            if len(chosen) >= max_acts:
                break
            if x not in chosen and kinds.get(x["kind"], 0) < max(2, max_acts // 3):
                kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
                chosen.append(x)
        acts = sorted(chosen[:max(max_acts, len(kinds))], key=lambda x: x["at"])
    if not acts:
        acts = [{"kind": "silence", "at": a.isoformat(), "weight": 0,
                 "functions": [{"function": "silence", "at": a.isoformat()}]}]
    return acts


def feasts(c: Cluster, a: datetime, b: datetime) -> list[dict]:
    """Crowds: load far above the cluster's normal for at least two hours —
    a sale, a closing, a launch. The guests keep arriving."""
    load = _seasonal_ratio(c)
    ia, ib = _i(a), _i(b)
    hot = load[ia:ib] > 1.8
    out, i = [], 0
    while i < len(hot):
        if not hot[i]:
            i += 1
            continue
        j = i
        while j < len(hot) and (hot[j] or hot[j:j + 12].any()):
            j += 1
        if j - i >= 24:
            peak = float(load[ia + i:ia + j].max())
            out.append({"kind": "crowd", "at": _t(ia + i).isoformat(), "weight": round(min(1, peak / 5), 3),
                        "functions": [{"function": "crowd", "at": _t(ia + i).isoformat(),
                                       "until": _t(ia + j).isoformat(), "peak_load": round(peak, 2)}]})
        i = j
    return out


_RATIO = {}


def _seasonal_ratio(c: Cluster) -> np.ndarray:
    """Load against the usual load of the same hour of the week, so a busy
    evening is normal and only an unusual crowd stands out."""
    if c.name not in _RATIO:
        load = c.signals["load"].astype(float)
        week = 7 * 288
        idx = np.arange(len(load)) % week
        base = np.array([np.median(load[idx == k]) for k in range(week)])
        _RATIO[c.name] = load / np.maximum(base[idx], 1e-6)
    return _RATIO[c.name]


def fasts(c: Cluster, a: datetime, b: datetime) -> list[dict]:
    """Freezes: no releases allowed — a fast, a vigil before the feast."""
    out = []
    for f in c.facts.get("freezes", []):
        fa = datetime.fromisoformat(f["from"]).replace(tzinfo=c.zone).astimezone(timezone.utc)
        if a <= fa < b:
            out.append({"kind": "fast", "at": fa.isoformat(), "weight": 0.5,
                        "functions": [{"function": "fast", "at": fa.isoformat(), "until": f["to"]}]})
    return out


def characters(c: Cluster, acts: list[dict]) -> list[dict]:
    """Who took part. Services carry a temperament from their whole year."""
    names = set()
    for act in acts:
        for f in act["functions"]:
            if f.get("who"):
                names.add(f["who"])
            names.update(f.get("affected", []))
    incidents_by = {}
    for x in c.facts["incidents"]:
        incidents_by[x["service"]] = incidents_by.get(x["service"], 0) + 1
    svcs = {s["name"]: s for s in c.facts["services"]}
    people = set(c.facts["people"])
    out = []
    for n in sorted(names):
        if n in svcs:
            k = incidents_by.get(n, 0)
            out.append({"id": f"service/{n}", "kind": svcs[n]["kind"], "role": ROLE[svcs[n]["kind"]],
                        "temperament": "nervous" if k >= 4 else "steady" if k <= 1 else "restless"})
        elif n in people:
            out.append({"id": f"person/{n}", "kind": "person", "role": "the one on watch"})
        elif n in ("horizontal-pod-autoscaler", "cluster-autoscaler"):
            out.append({"id": f"controller/{n}", "kind": "controller", "role": "the helper who multiplies"})
        else:
            out.append({"id": f"tenant/{n}", "kind": "tenant", "role": "a household"})
    return out


ROLE = {
    "web": "the face that meets everyone",
    "api": "the worker who carries the load",
    "db": "the keeper of memory",
    "cache": "the short memory",
    "worker": "the night labourer",
}


def curve(c: Cluster, a: datetime, b: datetime, points: int = 96) -> list[float]:
    """The tension curve of a window, resampled to a fixed number of points
    (the max of each bucket, so a short spike survives)."""
    seg = c.tension[_i(a):_i(b)]
    if len(seg) == 0:
        return []
    edges = np.linspace(0, len(seg), points + 1).astype(int)
    return [round(float(seg[edges[k]:max(edges[k + 1], edges[k] + 1)].max()), 3) for k in range(points)]


def material(c: Cluster, a: datetime, b: datetime, label: str) -> dict:
    acts = skeleton(c, a, b)
    return {
        "cluster": c.name,
        "window": label,
        "from": a.isoformat(),
        "to": b.isoformat(),
        "tension": curve(c, a, b),
        "skeleton": acts,
        "characters": characters(c, acts),
    }


# The windows of stage A (§59.3): nested around Black Friday for shop and bank.
STAGE_A = [
    ("year", "2025"), ("quarter", "2025-Q4"), ("month", "2025-11"),
    ("week", "2025-W48"), ("day", "2025-11-28"),
]


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Material of the stage A windows.")
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--out", type=Path, default=Path("out/material"))
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    args = ap.parse_args()
    for name in args.clusters:
        c = load(args.scenarios, name)
        d = args.out / name
        d.mkdir(parents=True, exist_ok=True)
        wins = [window(c, k, s) for k, s in STAGE_A]
        if name == "shop":
            main_incident = max(c.facts["incidents"], key=lambda x: x["severity"])
            wins.append(incident_window(c, main_incident))
        for a, b, label in wins:
            m = material(c, a, b, label)
            (d / (label.replace(":", "_") + ".json")).write_text(json.dumps(m, ensure_ascii=False, indent=1))
            fs = [f["function"] for act in m["skeleton"] for f in act["functions"]]
            print(f"{name:8} {label:42} acts={len(m['skeleton']):2} {' → '.join(fs)[:150]}")


if __name__ == "__main__":
    main()
