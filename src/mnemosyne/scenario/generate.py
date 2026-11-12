"""A year in the life of a cluster.

The generator plays a personality (scenarios/*.yaml) over 2025 on a
five-minute grid and writes three things:

* ops.jsonl — every change of a Kubernetes object, with its author: a human,
  GitOps or a controller. Human and GitOps changes are the cluster's intent;
  controller changes are its performance.
* signals.npz — what an observer of the cluster would measure: load, unready
  pods, warning events, latency, nodes, replicas, running cron jobs.
* facts.json — incidents, upgrades, migrations, freezes, tenants: the ground
  truth the material of a night is checked against.

Everything is driven by one seed, so a scenario is reproducible.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import yaml

from . import manifests as m

STEP = timedelta(minutes=5)
YEAR_START = datetime(2025, 1, 1, tzinfo=timezone.utc)
YEAR_END = datetime(2026, 1, 1, tzinfo=timezone.utc)
STEPS = int((YEAR_END - YEAR_START) / STEP)
PER_DAY = 288

DEPLOY_FAILURE = {"startup": 0.02, "leonia": 0.018, "ml": 0.03, "bank": 0.03}
TENANT_WORDS = [
    "aurora", "borealis", "cedar", "delta", "ember", "fjord", "garnet", "harbor", "iris", "juniper",
    "kestrel", "lumen", "meridian", "nova", "onyx", "prairie", "quartz", "raven", "sierra", "tundra",
    "umber", "vesper", "willow", "xenon", "yarrow", "zephyr",
]


@dataclass
class Op:
    at: datetime
    actor: str          # who: a person, a GitOps tool, a controller
    actor_kind: str     # human | gitops | controller
    op: str             # create | update | delete
    obj: dict
    reason: str = ""

    def json(self) -> str:
        return json.dumps({
            "at": self.at.isoformat(), "actor": self.actor, "actor_kind": self.actor_kind,
            "op": self.op, "reason": self.reason, "object": self.obj,
        }, ensure_ascii=False, sort_keys=True)


@dataclass
class World:
    p: dict
    rng: np.random.Generator
    ops: list[Op] = field(default_factory=list)
    objects: dict = field(default_factory=dict)   # (kind, ns, name) -> object
    tags: dict = field(default_factory=dict)      # service -> current image tag
    prev_tags: dict = field(default_factory=dict)
    incidents: list[dict] = field(default_factory=list)
    tenants: list[dict] = field(default_factory=list)
    people: list[str] = field(default_factory=list)

    def key(self, obj):
        md = obj["metadata"]
        return (obj["kind"], md.get("namespace", ""), md["name"])

    def apply(self, at, actor, kind, op, obj, reason=""):
        k = self.key(obj)
        if op == "delete":
            self.objects.pop(k, None)
        else:
            op = "update" if k in self.objects else "create"
            self.objects[k] = copy.deepcopy(obj)
        self.ops.append(Op(at, actor, kind, op, copy.deepcopy(obj), reason))


def _bump(h, centre, width):
    d = np.minimum(np.abs(h - centre), 24 - np.abs(h - centre))
    return np.exp(-0.5 * (d / width) ** 2)


def _daily(profile: str, hour: np.ndarray, weekday: np.ndarray) -> np.ndarray:
    if profile == "evening":
        return 0.25 + 0.75 * _bump(hour, 20.5, 2.5) + 0.3 * _bump(hour, 13, 1.5)
    if profile == "business":
        on = ((hour >= 8) & (hour < 18)).astype(float)
        return 0.12 + 0.88 * on * (1 + 0.15 * _bump(hour, 11, 1.5))
    if profile == "night":
        return 0.3 + 0.7 * np.maximum(_bump(hour, 2, 3), 0.2 * _bump(hour, 14, 4))
    return 0.55 + 0.3 * _bump(hour, 15, 5)


def _local_clock(tz: str):
    """Local hour (fractional), weekday and date of every step."""
    zone = ZoneInfo(tz)
    hours = np.empty(STEPS)
    weekday = np.empty(STEPS, dtype=int)
    days = []
    for d in range(STEPS // PER_DAY):
        t0 = YEAR_START + d * PER_DAY * STEP
        off = t0.astimezone(zone).utcoffset().total_seconds() / 3600
        sl = slice(d * PER_DAY, (d + 1) * PER_DAY)
        local = (np.arange(PER_DAY) * 5 / 60 + off) % 24
        hours[sl] = local
        weekday[sl] = (t0 + timedelta(hours=off)).weekday()
        days.append((t0 + timedelta(hours=off)).date())
    return hours, weekday, days


def _when(i: int) -> datetime:
    return YEAR_START + i * STEP


def _index(t: datetime) -> int:
    return max(0, min(STEPS - 1, int((t - YEAR_START) / STEP)))


def _parse(s: str, tz: str) -> datetime:
    t = datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=ZoneInfo(tz))
    return t.astimezone(timezone.utc)


def _load(p: dict, rng) -> np.ndarray:
    hour, weekday, days = _local_clock(p["timezone"])
    load = _daily(p["daily_profile"], hour, weekday)
    wk = p.get("weekly", {})
    load *= np.where(weekday == 5, wk.get("sat", 1.0), 1.0) * np.where(weekday == 6, wk.get("sun", 1.0), 1.0)
    for s in p.get("seasons", []):
        a, b = _index(_parse(s["from"], p["timezone"])), _index(_parse(s["to"], p["timezone"]))
        ramp = np.ones(b - a)
        k = min(PER_DAY // 2, (b - a) // 4)
        if k:
            ramp[:k] = np.linspace(0.3, 1, k)
            ramp[-k:] = np.linspace(1, 0.3, k)
        load[a:b] *= 1 + (s["factor"] - 1) * ramp
    if p.get("month_end_factor"):
        for i, d in enumerate(days):
            nxt = d + timedelta(days=1)
            if nxt.month != d.month:
                load[i * PER_DAY:(i + 1) * PER_DAY] *= p["month_end_factor"]
    noise = np.zeros(STEPS)
    e = rng.normal(0, 0.06, STEPS)
    for i in range(1, STEPS):
        noise[i] = 0.97 * noise[i - 1] + e[i]
    return load * np.exp(noise)


def _bump_tag(tag: str, rng) -> str:
    major, minor, patch = (int(x) for x in tag.split("."))
    r = rng.random()
    if r < 0.03:
        return f"{major + 1}.0.0"
    if r < 0.3:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _in_freeze(p, t):
    return any(_parse(f["from"], p["timezone"]) <= t < _parse(f["to"], p["timezone"]) for f in p.get("freezes", []))


def _working_moment(p, rng, day_start: datetime) -> datetime:
    """A moment people deploy: a weekday, office hours, local time."""
    zone = ZoneInfo(p["timezone"])
    local = day_start.astimezone(zone).replace(hour=0, minute=0)
    h = rng.normal(13.5, 2.2)
    return (local + timedelta(hours=float(np.clip(h, 9.5, 18.5)))).astimezone(timezone.utc)


def _initial_state(w: World, nodes_now: int):
    p = w.p
    t = YEAR_START - timedelta(days=30)
    admin = w.people[0]
    ns = p["name"]
    w.apply(t, admin, "human", "create", m.namespace(ns, {"team": "platform"}))
    for svc in p["services"]:
        tag = m.BASE_TAG.get(svc["kind"], f"1.{int(w.rng.integers(0, 12))}.{int(w.rng.integers(0, 9))}")
        w.tags[svc["name"]] = tag
        w.apply(t, "argocd", "gitops", "create", m.workload(ns, svc, tag, svc["replicas"]))
        w.apply(t, "argocd", "gitops", "create", m.service(ns, svc))
        w.apply(t, "argocd", "gitops", "create", m.config(ns, svc, {"LOG_LEVEL": "info", "FEATURE_FLAGS": ""}))
        if svc["kind"] in ("web", "api"):
            w.apply(t, "argocd", "gitops", "create", m.hpa(ns, svc, svc["replicas"]))
        if svc["kind"] == "web":
            w.apply(t, "argocd", "gitops", "create", m.ingress(ns, f"{svc['name']}.{ns}.example.com", svc))
    for cj in p.get("cronjobs", []):
        w.apply(t, "argocd", "gitops", "create", m.cronjob(ns, cj["name"], cj["schedule"], "1.0.0"))
    if p.get("strict_network_policies"):
        w.apply(t, admin, "human", "create", m.default_deny(ns))
        callers: dict[str, list[str]] = {}
        for svc in p["services"]:
            for d in svc["deps"]:
                callers.setdefault(d, []).append(svc["name"])
        for target, sources in callers.items():
            port = m.PORTS[next(s for s in p["services"] if s["name"] == target)["kind"]]
            w.apply(t, admin, "human", "create", m.allow_from(ns, target, sources, port))
    for _ in range(p["tenants"]["initial"]):
        _tenant_birth(w, t)
    region = (p.get("migration") or {}).get("from", "eu-central")
    for n in range(nodes_now):
        w.apply(t, "cluster-autoscaler", "controller", "create",
                m.node(f"{ns}-node-{n:03d}", region, f"{region}-{n % 3 + 1}", p["k8s_upgrade"]["from"]))


def _tenant_birth(w: World, t: datetime):
    p = w.p
    word = TENANT_WORDS[len(w.tenants) % len(TENANT_WORDS)]
    name = (f"exp-{word}-{len(w.tenants)}" if p["name"] == "ml" else f"team-{word}")
    owner = w.people[int(w.rng.integers(0, len(w.people)))]
    svc = {"name": f"{word}-app", "kind": "api", "replicas": 2, "deps": []}
    w.apply(t, owner, "human", "create", m.namespace(name, {"tenant": "true"}))
    w.apply(t, owner, "human", "create", m.workload(name, svc, "0.1.0", 2))
    w.apply(t, owner, "human", "create", m.service(name, svc))
    w.apply(t, owner, "human", "create", m.default_deny(name))
    w.tenants.append({"name": name, "born": t.isoformat(), "died": None, "owner": owner, "app": svc["name"]})


def _tenant_death(w: World, t: datetime):
    alive = [x for x in w.tenants if x["died"] is None]
    if len(alive) <= 1:
        return
    x = alive[int(w.rng.integers(0, len(alive)))]
    for k in [k for k in w.objects if k[1] == x["name"]]:
        w.apply(t, x["owner"], "human", "delete", w.objects[k], reason="tenant removed")
    w.apply(t, x["owner"], "human", "delete", m.namespace(x["name"]), reason="tenant removed")
    x["died"] = t.isoformat()


PEOPLE = {
    "leonia": ["marta.k", "jonas.b", "lea.w", "tim.r"],
    "bank": ["urs.f", "claudia.m", "reto.s"],
    "ml": ["priya.n", "diego.a", "sam.o", "hana.k", "lukas.v"],
    "startup": ["ines.c", "rui.p"],
}


def simulate(p: dict) -> tuple[World, dict, dict]:
    rng = np.random.default_rng(p["seed"])
    w = World(p=p, rng=rng, people=PEOPLE.get(p["name"], ["admin"]))
    ns = p["name"]
    svcs = {s["name"]: s for s in p["services"]}
    dependents: dict[str, list[str]] = {s: [] for s in svcs}
    for s in p["services"]:
        for d in s["deps"]:
            dependents.setdefault(d, []).append(s["name"])

    load = _load(p, rng)
    base = np.median(load)
    rel = load / base
    nodes_n = np.clip(np.round(p["nodes"]["initial"] * (0.7 + 0.3 * rel)), 3, p["nodes"]["max"]).astype(int)
    _initial_state(w, int(nodes_n[0]))

    unready = np.zeros(STEPS)
    warnings = rng.poisson(0.3, STEPS).astype(float)
    latency = 80 * (1 + 0.25 * np.maximum(rel - 1, 0)) * np.exp(rng.normal(0, 0.05, STEPS))

    # Deploys: people ship on weekdays, not during freezes; some deploys break things.
    events = []
    weeks = 53
    for wk in range(weeks):
        n = rng.poisson(p["deploys_per_week"])
        for _ in range(n):
            day = YEAR_START + timedelta(days=wk * 7 + int(rng.integers(0, 5)))
            t = _working_moment(p, rng, day)
            if t >= YEAR_END or _in_freeze(p, t):
                continue
            target = [s for s in p["services"] if s["kind"] in ("web", "api", "worker")]
            svc = target[int(rng.integers(0, len(target)))]
            events.append(("deploy", t, svc["name"]))
    # Spontaneous incidents, more likely under load.
    for month in range(12):
        for _ in range(rng.poisson(p["incidents_per_month"] * 0.6)):
            a = int((datetime(2025, month + 1, 1, tzinfo=timezone.utc) - YEAR_START) / STEP)
            span = 28 * PER_DAY
            weights = rel[a:a + span] ** 2
            i = a + int(rng.choice(len(weights), p=weights / weights.sum()))
            svc = p["services"][int(rng.integers(0, len(p["services"])))]["name"]
            events.append(("incident", _when(i), svc, "load" if rel[i] > 1.5 else "fault"))
    for f in p.get("forced_incidents", []):
        events.append(("incident", _parse(f["at"], p["timezone"]), f["service"], f.get("cause", "load"), f))
    # Tenants.
    for q in range(4):
        for _ in range(rng.poisson(p["tenants"]["births_per_quarter"])):
            events.append(("birth", YEAR_START + timedelta(days=q * 91 + float(rng.uniform(0, 91)))))
        for _ in range(rng.poisson(p["tenants"]["deaths_per_quarter"])):
            events.append(("death", YEAR_START + timedelta(days=q * 91 + float(rng.uniform(0, 91)))))
    # Day-to-day tuning: config changes by people.
    for _ in range(int(p["deploys_per_week"] * 52 * 0.25)):
        day = YEAR_START + timedelta(days=float(rng.uniform(0, 364)))
        events.append(("tune", _working_moment(p, rng, day), p["services"][int(rng.integers(0, len(p["services"])))]["name"]))
    up = p["k8s_upgrade"]
    events.append(("upgrade", _parse(up["at"], p["timezone"])))
    if p.get("migration"):
        events.append(("migration", _parse(p["migration"]["at"], p["timezone"])))
    events.sort(key=lambda e: e[1])

    def incident(t, svc, cause, severity=None, minutes=None, deploy=None):
        i0 = _index(t)
        sev = severity if severity is not None else float(np.clip(rng.beta(2, 4) * (1.3 if cause == "load" else 1), 0.1, 1))
        dur = minutes if minutes is not None else float(np.clip(rng.lognormal(math.log(35), 0.8), 8, 600)) * (0.6 + sev)
        n = max(2, int(dur / 5))
        i1 = min(STEPS, i0 + n)
        shape = np.sin(np.linspace(0.15, math.pi * 0.95, i1 - i0)) ** 0.6
        hit = [svc] + dependents.get(svc, [])
        unready[i0:i1] += sev * 0.6 * shape * (1 + 0.3 * (len(hit) - 1))
        warnings[i0:i1] += rng.poisson(6 * sev * len(hit), i1 - i0) * shape
        latency[i0:i1] *= 1 + 4 * sev * shape
        rec = {"start": _when(i0).isoformat(), "end": _when(i1).isoformat(), "service": svc,
               "affected": hit, "severity": round(sev, 3), "cause": cause, "actions": []}
        # The on-call person notices and acts.
        oncall = w.people[int(rng.integers(0, len(w.people)))]
        t_act = _when(i0) + timedelta(minutes=float(rng.uniform(4, 18)))
        if deploy and deploy in w.prev_tags:
            w.tags[deploy] = w.prev_tags[deploy]
            obj = copy.deepcopy(w.objects[("Deployment", ns, deploy)])
            obj["spec"]["template"]["spec"]["containers"][0]["image"] = m.image(svcs[deploy], w.tags[deploy])
            w.apply(t_act, oncall, "human", "update", obj, reason=f"rollback {deploy}")
            rec["actions"].append({"at": t_act.isoformat(), "by": oncall, "what": "rollback", "service": deploy})
        else:
            kind = "StatefulSet" if svcs[svc]["kind"] in ("db", "cache") else "Deployment"
            obj = copy.deepcopy(w.objects[(kind, ns, svc)])
            if kind == "Deployment" and rng.random() < 0.6:
                obj["spec"]["replicas"] = obj["spec"]["replicas"] + int(rng.integers(1, 4))
                what = "scale-up"
            else:
                ann = obj["spec"]["template"]["metadata"].setdefault("annotations", {})
                ann["kubectl.kubernetes.io/restartedAt"] = t_act.isoformat()
                what = "restart"
            w.apply(t_act, oncall, "human", "update", obj, reason=f"{what} during incident")
            rec["actions"].append({"at": t_act.isoformat(), "by": oncall, "what": what, "service": svc})
        if sev > 0.5 and rng.random() < 0.7:
            t2 = t_act + timedelta(minutes=float(rng.uniform(10, 40)))
            cm = copy.deepcopy(w.objects[("ConfigMap", ns, svc + "-config")])
            cm["data"]["FEATURE_FLAGS"] = "degraded-mode"
            w.apply(t2, oncall, "human", "update", cm, reason="degraded mode during incident")
            rec["actions"].append({"at": t2.isoformat(), "by": oncall, "what": "degraded-mode", "service": svc})
            t3 = _when(i1) + timedelta(minutes=float(rng.uniform(5, 60)))
            cm = copy.deepcopy(cm)
            cm["data"]["FEATURE_FLAGS"] = ""
            w.apply(t3, oncall, "human", "update", cm, reason="back to normal after incident")
            rec["actions"].append({"at": t3.isoformat(), "by": oncall, "what": "normal-mode", "service": svc})
        w.incidents.append(rec)

    zone_region = (p.get("migration") or {}).get("from", "eu-central")
    version = up["from"]
    for e in events:
        kind, t = e[0], e[1]
        if kind == "deploy":
            svc = svcs[e[2]]
            w.prev_tags[svc["name"]] = w.tags[svc["name"]]
            w.tags[svc["name"]] = _bump_tag(w.tags[svc["name"]], rng)
            obj = copy.deepcopy(w.objects[("Deployment", ns, svc["name"])])
            obj["spec"]["template"]["spec"]["containers"][0]["image"] = m.image(svc, w.tags[svc["name"]])
            actor = "argocd" if rng.random() < 0.8 else w.people[int(rng.integers(0, len(w.people)))]
            w.apply(t, actor, "gitops" if actor == "argocd" else "human", "update", obj, reason=f"release {w.tags[svc['name']]}")
            if rng.random() < DEPLOY_FAILURE.get(p["name"], 0.03):
                incident(t + timedelta(minutes=float(rng.uniform(2, 25))), svc["name"], "deploy", deploy=svc["name"])
        elif kind == "incident":
            extra = e[4] if len(e) > 4 else {}
            incident(t, e[2], e[3], extra.get("severity"), extra.get("minutes"))
        elif kind == "birth":
            _tenant_birth(w, t)
        elif kind == "death":
            _tenant_death(w, t)
        elif kind == "tune":
            svc = svcs[e[2]]
            cm = copy.deepcopy(w.objects[("ConfigMap", ns, svc["name"] + "-config")])
            cm["data"]["LOG_LEVEL"] = str(rng.choice(["info", "debug", "warn"]))
            cm["data"]["POOL_SIZE"] = str(int(rng.integers(4, 64)))
            w.apply(t, w.people[int(rng.integers(0, len(w.people)))], "human", "update", cm, reason="tuning")
        elif kind == "upgrade":
            version = up["to"]
            for k in [k for k in w.objects if k[0] == "Node"]:
                node = copy.deepcopy(w.objects[k])
                node["metadata"]["labels"]["node.kubernetes.io/kubelet-version"] = "v" + version
                w.apply(t + timedelta(minutes=2 * len(w.ops) % 90), "cluster-upgrade", "controller", "update", node, reason=f"upgrade to {version}")
        elif kind == "migration":
            mig = p["migration"]
            zone_region = mig["to"]
            for k in [k for k in w.objects if k[0] == "Node"]:
                w.apply(t, "cluster-autoscaler", "controller", "delete", w.objects[k], reason="migration")
            for n in range(int(nodes_n[_index(t)])):
                w.apply(t + timedelta(minutes=10), "cluster-autoscaler", "controller", "create",
                        m.node(f"{ns}-{mig['to']}-node-{n:03d}", mig["to"], f"{mig['to']}-{n % 3 + 1}", version))
            incident(t + timedelta(minutes=20), "postgres" if "postgres" in svcs else p["services"][0]["name"], "migration", 0.55, 70)

    # Performance: the autoscalers follow the load; these are consequences, not intent.
    replicas_total = np.zeros(STEPS)
    for svc in p["services"]:
        r = np.full(STEPS, float(svc["replicas"]))
        if svc["kind"] in ("web", "api"):
            r = np.clip(np.ceil(svc["replicas"] * rel * svc["share"] / 0.7), svc["replicas"], svc["replicas"] * 6)
            last, last_i = r[0], 0
            for i in range(PER_DAY, STEPS, 3):
                if r[i] != last and i - last_i >= 6:
                    obj = copy.deepcopy(w.objects.get(("Deployment", ns, svc["name"])))
                    if obj:
                        obj["spec"]["replicas"] = int(r[i])
                        w.apply(_when(i), "horizontal-pod-autoscaler", "controller", "update", obj, reason="autoscale")
                    last, last_i = r[i], i
        replicas_total += r
    prev = int(nodes_n[0])
    for i in range(PER_DAY, STEPS, 6):
        cur = int(nodes_n[i])
        if cur != prev:
            existing = sorted(k for k in w.objects if k[0] == "Node")
            if cur > len(existing):
                for n in range(len(existing), cur):
                    w.apply(_when(i), "cluster-autoscaler", "controller", "create",
                            m.node(f"{ns}-node-x{i:06d}-{n}", zone_region, f"{zone_region}-{n % 3 + 1}", version))
            else:
                for k in existing[cur:]:
                    w.apply(_when(i), "cluster-autoscaler", "controller", "delete", w.objects[k], reason="scale down")
            prev = cur

    hour, _, _ = _local_clock(p["timezone"])
    cron_active = np.zeros(STEPS)
    for cj in p.get("cronjobs", []):
        minute, hr = cj["schedule"].split()[:2]
        if hr.isdigit():
            cron_active += (np.abs(hour - (int(hr) + (int(minute) if minute.isdigit() else 0) / 60)) < 0.25)
    w.ops.sort(key=lambda o: o.at)
    # The autoscaler was simulated after the year, from the final objects:
    # give each of its changes the pod template people had set at that moment.
    templates: dict = {}
    for o in w.ops:
        if o.obj["kind"] != "Deployment":
            continue
        k = (o.obj["metadata"].get("namespace", ""), o.obj["metadata"]["name"])
        if o.actor_kind == "controller":
            if k in templates:
                o.obj["spec"]["template"] = copy.deepcopy(templates[k])
        else:
            templates[k] = copy.deepcopy(o.obj["spec"]["template"])
    signals = {
        "load": rel.astype(np.float32),
        "unready": np.clip(unready, 0, 1).astype(np.float32),
        "warnings": warnings.astype(np.float32),
        "latency_ms": latency.astype(np.float32),
        "nodes": nodes_n.astype(np.int16),
        "replicas": replicas_total.astype(np.float32),
        "cron_active": cron_active.astype(np.float32),
    }
    facts = {
        "cluster": p["name"], "timezone": p["timezone"], "people": w.people,
        "start": YEAR_START.isoformat(), "step_minutes": 5,
        "incidents": sorted(w.incidents, key=lambda x: x["start"]),
        "tenants": w.tenants,
        "upgrade": {**up, "at_utc": _parse(up["at"], p["timezone"]).isoformat()},
        "migration": p.get("migration"),
        "freezes": p.get("freezes", []),
        "seasons": p.get("seasons", []),
        "services": p["services"],
    }
    return w, signals, facts


def run(scenario: Path, out: Path) -> dict:
    p = yaml.safe_load(scenario.read_text())
    w, signals, facts = simulate(p)
    d = out / p["name"]
    d.mkdir(parents=True, exist_ok=True)
    with (d / "ops.jsonl").open("w") as f:
        for o in w.ops:
            f.write(o.json() + "\n")
    np.savez_compressed(d / "signals.npz", **signals)
    (d / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    kinds = {}
    for o in w.ops:
        kinds[o.actor_kind] = kinds.get(o.actor_kind, 0) + 1
    return {"cluster": p["name"], "ops": len(w.ops), "by_actor": kinds, "incidents": len(w.incidents),
            "tenants": len(w.tenants), "objects_at_end": len(w.objects)}


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Generate a year in the life of clusters.")
    ap.add_argument("scenarios", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/scenarios"))
    a = ap.parse_args()
    for s in a.scenarios:
        print(json.dumps(run(s, a.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
