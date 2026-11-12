"""The building of a year: built month by month, never erased.

A cathedral is read from its stones: the Romanesque nave, the Gothic
choir, the chapel added after a fire. The building of a cluster is made
the same way. Each month is a building campaign: rooms for the services
and households that appeared are added next to the rooms they depend on,
and what is built stays where it is. A household that left becomes a
ruin; rooms that lived through an incident carry golden seams, as broken
bowls do in kintsugi; after a major upgrade the building continues in
another manner. The result is a phase plan, coloured by month as
archaeologists colour building phases, an axonometric view with
superstructures where a service grew, and twelve monthly plans as the
building's chronicle.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ortools.sat.python import cp_model

from .architecture import CELL_M, ROOM

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Phase colours: cool at the start of the year, warm at its end.
PHASE = ["#d9e2ec", "#c9d8e6", "#bfd3d6", "#c6dcc4", "#d6e3b8", "#e6e2ae",
         "#eedaa6", "#efcf9e", "#eabf96", "#e3ad8f", "#d99b8a", "#cf8a86"]
GOLD = "#c9a227"


def month_states(ops_path: Path, tz: str):
    """Objects present at the end of each month, and replica peaks."""
    zone = ZoneInfo(tz)
    ends = [datetime(2025, m + 1, 1, tzinfo=zone).astimezone(timezone.utc) if m < 12 else
            datetime(2026, 1, 1, tzinfo=zone).astimezone(timezone.utc) for m in range(1, 13)]
    objs, out, peak, i = {}, [], {}, 0
    month_peak: list[dict] = []
    for line in ops_path.open():
        o = json.loads(line)
        t = datetime.fromisoformat(o["at"])
        while i < 12 and t >= ends[i]:
            out.append({k: v for k, v in objs.items()})
            month_peak.append(dict(peak))
            i += 1
        md = o["object"]["metadata"]
        k = (o["object"]["kind"], md.get("namespace", ""), md["name"])
        if o["op"] == "delete":
            objs.pop(k, None)
        else:
            objs[k] = o["object"]
            if k[0] == "Deployment":
                peak[k] = max(peak.get(k, 0), int(o["object"]["spec"].get("replicas", 1)))
    while i < 12:
        out.append(dict(objs))
        month_peak.append(dict(peak))
        i += 1
    return out, peak, month_peak


def rooms_of(objs: dict, cluster: str) -> dict:
    rooms = {}
    for (kind, ns, name), o in objs.items():
        if kind in ("Deployment", "StatefulSet"):
            comp = o["metadata"].get("labels", {}).get("app.kubernetes.io/component", "api")
            tenant = ns != cluster
            reps = int(o["spec"].get("replicas", 1))
            rooms[f"{ns}/{name}"] = {"id": f"{ns}/{name}", "kind": "tenant" if tenant else comp,
                                     "use": ROOM["tenant" if tenant else comp],
                                     "cells": 4 if tenant else 4 + 2 * min(reps, 6)}
    return rooms


def place(new: list[dict], fixed: list[dict], wishes: list[tuple[str, str]], seconds: float, seed: int) -> list[dict]:
    """Place new rooms around the fixed ones: no overlaps, next to what they
    depend on, keeping the building compact."""
    if not new:
        return []
    total = sum(r["cells"] for r in new) + sum(r["w"] * r["h"] for r in fixed)
    ext = int((total * 2.2) ** 0.5) + 8
    lo, hi = -ext, ext
    m = cp_model.CpModel()
    xi, yi, var = [], [], {}
    for r in fixed:
        xi.append(m.new_fixed_size_interval_var(r["x"], r["w"], f"fx{r['id']}"))
        yi.append(m.new_fixed_size_interval_var(r["y"], r["h"], f"fy{r['id']}"))
    for r in new:
        i = r["id"]
        x, y = m.new_int_var(lo, hi, f"x{i}"), m.new_int_var(lo, hi, f"y{i}")
        w, h = m.new_int_var(2, 10, f"w{i}"), m.new_int_var(2, 10, f"h{i}")
        xe, ye = m.new_int_var(lo, hi + 10, f"xe{i}"), m.new_int_var(lo, hi + 10, f"ye{i}")
        m.add(xe == x + w)
        m.add(ye == y + h)
        a = m.new_int_var(r["cells"], r["cells"] * 2, f"a{i}")
        m.add_multiplication_equality(a, [w, h])
        m.add(w <= 3 * h)
        m.add(h <= 3 * w)
        xi.append(m.new_interval_var(x, w, xe, f"ix{i}"))
        yi.append(m.new_interval_var(y, h, ye, f"iy{i}"))
        var[i] = (x, y, w, h)
    m.add_no_overlap_2d(xi, yi)
    geo = {r["id"]: (r["x"], r["y"], r["w"], r["h"]) for r in fixed}
    geo.update(var)
    sat = []
    for a, b in wishes:
        if a not in geo or b not in geo or (a not in var and b not in var):
            continue
        (xa, ya, wa, ha), (xb, yb, wb, hb) = geo[a], geo[b]
        side = [m.new_bool_var("") for _ in range(4)]
        m.add(xa + wa == xb).only_enforce_if(side[0])
        m.add(xb + wb == xa).only_enforce_if(side[1])
        m.add(ya + ha == yb).only_enforce_if(side[2])
        m.add(yb + hb == ya).only_enforce_if(side[3])
        for k in (0, 1):
            m.add(ya + 1 <= yb + hb).only_enforce_if(side[k])
            m.add(yb + 1 <= ya + ha).only_enforce_if(side[k])
        for k in (2, 3):
            m.add(xa + 1 <= xb + wb).only_enforce_if(side[k])
            m.add(xb + 1 <= xa + wa).only_enforce_if(side[k])
        ok = m.new_bool_var("")
        m.add_bool_or(side).only_enforce_if(ok)
        sat.append(ok)
    # Compactness: new rooms stay near the centre of what is built.
    cx = sum(r["x"] + r["w"] / 2 for r in fixed) / len(fixed) if fixed else 0
    cy = sum(r["y"] + r["h"] / 2 for r in fixed) / len(fixed) if fixed else 0
    dist = []
    for i, (x, y, w, h) in var.items():
        dx, dy = m.new_int_var(0, 4 * ext, ""), m.new_int_var(0, 4 * ext, "")
        m.add_abs_equality(dx, x - int(cx))
        m.add_abs_equality(dy, y - int(cy))
        dist += [dx, dy]
    m.maximize(30 * sum(sat) - sum(dist))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = seconds
    sv.parameters.random_seed = seed
    sv.parameters.num_workers = int(os.environ.get("SOLVER_WORKERS", "2"))
    st = sv.solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"no placement: {sv.status_name(st)}")
    return [{**r, "x": sv.value(var[r["id"]][0]), "y": sv.value(var[r["id"]][1]),
             "w": sv.value(var[r["id"]][2]), "h": sv.value(var[r["id"]][3])} for r in new]


def build_year(scenarios: Path, cluster: str, seconds: float = 15) -> dict:
    facts = json.loads((scenarios / cluster / "facts.json").read_text())
    states, peak, month_peak = month_states(scenarios / cluster / "ops.jsonl", facts["timezone"])
    base = {f"{cluster}/{sv['name']}": sv["replicas"] for sv in facts["services"]}
    annexed: dict[str, int] = {}
    record: dict[str, int] = {}
    wishes = sorted({tuple(sorted((f"{cluster}/{s['name']}", f"{cluster}/{d}"))) for s in facts["services"] for d in s["deps"]})
    upgrade_month = datetime.fromisoformat(facts["upgrade"]["at_utc"]).astimezone(ZoneInfo(facts["timezone"])).month
    built: dict[str, dict] = {}
    chronicle = []
    for mi, objs in enumerate(states):
        present = rooms_of(objs, cluster)
        # A household that left becomes a ruin; it is never demolished.
        for rid, r in built.items():
            host = r.get("annex_of", rid)
            if host not in present and not r.get("ruined"):
                r["ruined"] = MONTHS[mi]
        new = [r for rid, r in present.items() if rid not in built]
        # Tenant apartments wish to sit together, as one residential wing.
        flats = sorted([r["id"] for r in new if r["kind"] == "tenant"] +
                       [rid for rid, r in built.items() if r["kind"] == "tenant" and not r.get("ruined")])
        # The building swells where the crowd came: annexes.
        annex_wishes = []
        for (kind, ns, name), p in month_peak[mi].items():
            rid = f"{ns}/{name}"
            if kind != "Deployment" or rid not in base or (rid not in built and rid not in present):
                continue
            # A new record of size, a fifth above every month before, gets an
            # annex; January only sets the measure.
            if mi > 0 and p > record.get(rid, p) * 1.2 and annexed.get(rid, 0) < 3:
                annexed[rid] = annexed.get(rid, 0) + 1
                aid = f"{rid}#annex{annexed[rid]}"
                host = built.get(rid) or present[rid]
                new.append({"id": aid, "kind": host["kind"], "use": "Annex", "cells": 4, "annex_of": rid})
                annex_wishes.append((rid, aid))
            record[rid] = max(record.get(rid, 0), p)
        w = wishes + list(zip(flats, flats[1:])) + annex_wishes
        placed = place(new, list(built.values()), w, seconds, seed=mi)
        for r in placed:
            r["month"] = mi
            r["style"] = "after the upgrade" if mi + 1 >= upgrade_month else "first manner"
            built[r["id"]] = r
        chronicle.append({"month": MONTHS[mi], "new": [r["id"] for r in placed],
                          "ruined": [rid for rid, r in built.items() if r.get("ruined") == MONTHS[mi]],
                          "plan": [dict(r) for r in built.values()]})
    # Golden seams: rooms that lived through incidents.
    for inc in facts["incidents"]:
        for svc in inc["affected"]:
            rid = f"{cluster}/{svc}"
            if rid in built:
                built[rid]["seams"] = built[rid].get("seams", 0) + 1
                built[rid]["seam_severity"] = max(built[rid].get("seam_severity", 0), inc["severity"])
    for k, p in peak.items():
        rid = f"{k[1]}/{k[2]}"
        if rid in built:
            base = built[rid]["cells"]
            built[rid]["floors"] = 1 + (1 if p >= 8 else 0) + (1 if p >= 16 else 0) + (1 if built[rid]["kind"] == "web" else 0)
    return {"cluster": cluster, "upgrade_month": MONTHS[upgrade_month - 1], "rooms": list(built.values()),
            "chronicle": chronicle}


def _bbox(rooms):
    xs = [r["x"] for r in rooms] + [r["x"] + r["w"] for r in rooms]
    ys = [r["y"] for r in rooms] + [r["y"] + r["h"] for r in rooms]
    return min(xs), min(ys), max(xs), max(ys)


def phase_plan(rooms: list[dict], title: str, legend: bool = True, s: int = 26) -> str:
    x0, y0, x1, y1 = _bbox(rooms)
    W, H = (x1 - x0) * s, (y1 - y0) * s
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 260}" height="{H + 120}" font-family="Georgia, serif">',
           '<defs><pattern id="ruin" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           '<line x1="0" y1="0" x2="0" y2="8" stroke="#9a8f80" stroke-width="2"/></pattern></defs>',
           '<rect width="100%" height="100%" fill="#faf7f0"/>',
           f'<text x="30" y="34" font-size="18" fill="#333">{title}</text>', '<g transform="translate(30,60)">']
    for r in sorted(rooms, key=lambda r: r.get("month", 0)):
        x, y, w, h = (r["x"] - x0) * s, (y1 - r["y"] - r["h"]) * s, r["w"] * s, r["h"] * s
        fill = "url(#ruin)" if r.get("ruined") else PHASE[r.get("month", 0)]
        stroke = "#a89c88" if r.get("ruined") else "#333"
        dash = ' stroke-dasharray="6 4"' if r.get("ruined") else ""
        thick = 4 if r.get("style") == "after the upgrade" else 2.2
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{thick}"{dash}/>')
        if r.get("seams") and not r.get("ruined"):
            # Golden seams: a few thin cracks, mended with gold.
            import random

            rnd = random.Random(r["id"])
            for k in range(min(3, 1 + r["seams"] // 4)):
                px, py = x + w * rnd.uniform(0.15, 0.85), y
                pts = [(px, py)]
                while py < y + h:
                    py += h * rnd.uniform(0.12, 0.25)
                    px = min(x + w - 2, max(x + 2, px + w * rnd.uniform(-0.12, 0.12)))
                    pts.append((px, min(py, y + h)))
                out.append('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) +
                           f'" fill="none" stroke="{GOLD}" stroke-width="{1 + 1.5 * r.get("seam_severity", 0.3):.1f}"/>')
        label = r["use"] + (" (ruin)" if r.get("ruined") else "")
        out.append(f'<text x="{x + 5}" y="{y + 14}" font-size="10" fill="#333">{label}</text>')
        out.append(f'<text x="{x + 5}" y="{y + 26}" font-size="8.5" fill="#666">{MONTHS[r.get("month", 0)]}'
                   f'{" · " + r["ruined"] if r.get("ruined") else ""}</text>')
    out.append("</g>")
    if legend:
        lx = W + 60
        out.append(f'<text x="{lx}" y="76" font-size="12" fill="#333">Building campaigns</text>')
        for i, mname in enumerate(MONTHS):
            out.append(f'<rect x="{lx}" y="{86 + i * 18}" width="14" height="12" fill="{PHASE[i]}" stroke="#333" stroke-width="0.6"/>')
            out.append(f'<text x="{lx + 20}" y="{96 + i * 18}" font-size="10" fill="#333">{mname} 2025</text>')
        yy = 86 + 12 * 18 + 14
        out.append(f'<line x1="{lx}" y1="{yy}" x2="{lx + 14}" y2="{yy}" stroke="{GOLD}" stroke-width="3"/>'
                   f'<text x="{lx + 20}" y="{yy + 4}" font-size="10">golden seam: survived an incident</text>')
        out.append(f'<rect x="{lx}" y="{yy + 12}" width="14" height="12" fill="url(#ruin)" stroke="#a89c88"/>'
                   f'<text x="{lx + 20}" y="{yy + 22}" font-size="10">ruin: a household left</text>')
        out.append(f'<rect x="{lx}" y="{yy + 32}" width="14" height="12" fill="none" stroke="#333" stroke-width="4"/>'
                   f'<text x="{lx + 20}" y="{yy + 42}" font-size="10">thick walls: after the upgrade</text>')
    out.append("</svg>")
    return "\n".join(out)


def axonometric(rooms: list[dict], title: str, s: int = 18, floor_h: float = 1.2) -> str:
    """An isometric view: rooms as volumes, superstructures where a service grew."""
    import math

    cos, sin = math.cos(math.radians(30)), math.sin(math.radians(30))
    P = lambda x, y, z: ((x - y) * cos * s, (x + y) * sin * s - z * s)
    polys = []
    for r in sorted(rooms, key=lambda r: (r["x"] + r["y"])):
        z = 0.15 if r.get("ruined") else floor_h * r.get("floors", 1)
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        col = "#d8d0c2" if r.get("ruined") else PHASE[r.get("month", 0)]
        top = [P(x, y, z), P(x + w, y, z), P(x + w, y + h, z), P(x, y + h, z)]
        right = [P(x + w, y, 0), P(x + w, y + h, 0), P(x + w, y + h, z), P(x + w, y, z)]
        left = [P(x, y + h, 0), P(x + w, y + h, 0), P(x + w, y + h, z), P(x, y + h, z)]
        polys.append((left, _shade(col, 0.8)))
        polys.append((right, _shade(col, 0.65)))
        polys.append((top, col))
        if r.get("seams") and not r.get("ruined"):
            a, b = P(x + w * 0.3, y + h, z * 0.9), P(x + w * 0.45, y + h, z * 0.1)
            polys.append(([a, b], GOLD))
    pts = [p for poly, _ in polys for p in poly]
    minx, miny = min(p[0] for p in pts), min(p[1] for p in pts)
    maxx, maxy = max(p[0] for p in pts), max(p[1] for p in pts)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{maxx - minx + 60}" height="{maxy - miny + 90}" font-family="Georgia, serif">',
           '<rect width="100%" height="100%" fill="#faf7f0"/>', f'<text x="30" y="30" font-size="16">{title}</text>',
           f'<g transform="translate({30 - minx},{60 - miny})">']
    for poly, col in polys:
        if len(poly) == 2:
            out.append(f'<line x1="{poly[0][0]:.1f}" y1="{poly[0][1]:.1f}" x2="{poly[1][0]:.1f}" y2="{poly[1][1]:.1f}" stroke="{col}" stroke-width="2.5"/>')
        else:
            out.append('<polygon points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in poly) +
                       f'" fill="{col}" stroke="#444" stroke-width="0.8"/>')
    out.append("</g></svg>")
    return "\n".join(out)


def _shade(hexcol: str, k: float) -> str:
    c = [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(v * k):02x}" for v in c)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["leonia", "bank"])
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--out", type=Path, default=Path("out/works/architecture"))
    a = ap.parse_args()
    for c in a.clusters:
        y = build_year(a.scenarios, c)
        a.out.mkdir(parents=True, exist_ok=True)
        stem = f"{c}_year_2025"
        (a.out / f"{stem}_phases.svg").write_text(phase_plan(y["rooms"], f"{c} · the building of 2025 · phase plan"))
        (a.out / f"{stem}_axonometric.svg").write_text(axonometric(y["rooms"], f"{c} · the building of 2025"))
        sk = a.out / "sketches"
        sk.mkdir(exist_ok=True)
        for ch in y["chronicle"]:
            if ch["plan"]:
                (sk / f"{stem}_{ch['month']}.svg").write_text(phase_plan(ch["plan"], f"{c} · end of {ch['month']} 2025", legend=False))
        (a.out / f"{stem}.json").write_text(json.dumps(y, ensure_ascii=False, indent=1))
        print(c, len(y["rooms"]), "rooms;", sum(1 for r in y["rooms"] if r.get("ruined")), "ruins;",
              sum(1 for r in y["rooms"] if r.get("seams")), "with golden seams; upgrade in", y["upgrade_month"])


if __name__ == "__main__":
    main()
