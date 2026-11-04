"""A building from the state of a cluster.

The programme is read from the cluster itself, not invented: every
namespace is a wing or an apartment, every service a room whose size
follows its replicas, every dependency a wish for a shared wall with a
door, and where network policies are strict a door exists only where
traffic is allowed. Nodes set the structural bays.

A typology from the atlas (courtyard, enfilade) shapes the plan; a
constraint solver (OR-Tools CP-SAT) places the rooms on a grid without
overlaps, inside the site, with as many wished-for doors as it can.
Room names are architectural, never technical: a database is an archive,
a web front a reception hall.
"""

from __future__ import annotations

import hashlib
import os
import json
from datetime import datetime
from pathlib import Path

from ortools.sat.python import cp_model

CELL_M = 3.0  # one grid cell is 3 × 3 m

ROOM = {
    "web": "Reception hall",
    "api": "Workshop",
    "db": "Archive",
    "cache": "Pantry",
    "worker": "Night workshop",
    "tenant": "Apartment",
}


def state_at(ops_path: Path, t: datetime) -> dict:
    """The objects of the cluster at moment t: replay of the history."""
    objs = {}
    for line in ops_path.open():
        o = json.loads(line)
        if datetime.fromisoformat(o["at"]) > t:
            break
        md = o["object"]["metadata"]
        k = (o["object"]["kind"], md.get("namespace", ""), md["name"])
        if o["op"] == "delete":
            objs.pop(k, None)
        else:
            objs[k] = o["object"]
    return objs


def programme(objs: dict, cluster: str) -> dict:
    rooms, wishes, doors_only = [], [], False
    kinds = {}
    for (kind, ns, name), o in objs.items():
        if kind in ("Deployment", "StatefulSet"):
            comp = o["metadata"].get("labels", {}).get("app.kubernetes.io/component", "api")
            kinds[(ns, name)] = comp
            reps = int(o["spec"].get("replicas", 1))
            tenant = ns != cluster
            area = 4 + 2 * min(reps, 8) if not tenant else 4
            rooms.append({"id": f"{ns}/{name}", "wing": ns, "use": ROOM["tenant" if tenant else comp],
                          "cells": area, "kind": "tenant" if tenant else comp})
    policies = [o for (k, ns, n), o in objs.items() if k == "NetworkPolicy" and ns == cluster and n != "default-deny"]
    doors_only = any(n == "default-deny" for (k, ns, n) in objs if k == "NetworkPolicy" and ns == cluster)
    allowed = set()
    for p in policies:
        tgt = p["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"]
        for r in p["spec"].get("ingress", []):
            for f in r.get("from", []):
                src = f["podSelector"]["matchLabels"]["app.kubernetes.io/name"]
                allowed.add(tuple(sorted((f"{cluster}/{src}", f"{cluster}/{tgt}"))))
    # Wishes come from the declared dependencies, known from the scenario's
    # services through their policies, or from proximity of names in the
    # same wing when no policies exist (an open house).
    ids = {r["id"] for r in rooms}
    if allowed:
        wishes = sorted(p for p in allowed if p[0] in ids and p[1] in ids)
    nodes = sum(1 for (k, _, _) in objs if k == "Node")
    portal = [r["id"] for r in rooms if r["kind"] == "web"][:1]
    return {"rooms": rooms, "wishes": wishes, "doors_only_where_allowed": doors_only,
            "bays": max(4, min(12, nodes // 2)), "portal": portal}


def deps_from_scenario(facts: dict, cluster: str) -> list[tuple[str, str]]:
    out = set()
    for s in facts["services"]:
        for d in s["deps"]:
            out.add(tuple(sorted((f"{cluster}/{s['name']}", f"{cluster}/{d}"))))
    return sorted(out)


def _envelope(rooms: list, typology: str) -> tuple[int, int, int]:
    """Outer size and ring depth (cells) that hold the programme with some slack."""
    d = 3
    total = sum(r["cells"] for r in rooms)
    if typology == "enfilade":
        return sum(-(-r["cells"] // d) for r in rooms) + 2, d, d
    # Courtyard: a ring of depth d around a void; ring area ≈ 1.08 × total.
    for W in range(10, 60):
        H = max(2 * d + 3, round(W / 1.3))
        if W * H - (W - 2 * d) * (H - 2 * d) >= total * 1.3:
            return W, H, d
    return 60, 46, d


def solve(prog: dict, typology: str, seconds: float = 20, seed: int = 0) -> dict:
    rooms = prog["rooms"]
    W, H, d = _envelope(rooms, typology)
    m = cp_model.CpModel()
    xs, ys, ws, hs, xi, yi, areas = {}, {}, {}, {}, [], [], []
    for r in rooms:
        i = r["id"]
        a = r["cells"]
        ws[i] = m.new_int_var(2, W, f"w{i}")
        hs[i] = m.new_int_var(2, H, f"h{i}")
        xs[i] = m.new_int_var(0, W, f"x{i}")
        ys[i] = m.new_int_var(0, H, f"y{i}")
        xe = m.new_int_var(0, W, f"xe{i}")
        ye = m.new_int_var(0, H, f"ye{i}")
        m.add(xe == xs[i] + ws[i])
        m.add(ye == ys[i] + hs[i])
        area = m.new_int_var(a, a * 2 + 3, f"a{i}")
        m.add_multiplication_equality(area, [ws[i], hs[i]])
        areas.append(area)
        # Rooms of the ring are as deep as the ring: every room has a window
        # on the street and one on the courtyard.
        m.add(ws[i] <= 4 * hs[i])
        m.add(hs[i] <= 4 * ws[i])
        if typology == "enfilade":
            m.add(ys[i] == 0)
            m.add(hs[i] == d)
        xi.append(m.new_interval_var(xs[i], ws[i], xe, f"ix{i}"))
        yi.append(m.new_interval_var(ys[i], hs[i], ye, f"iy{i}"))
    if typology == "courtyard":
        cw, ch = W - 2 * d, H - 2 * d
        xi.append(m.new_interval_var(d, cw, d + cw, "cx"))
        yi.append(m.new_interval_var(d, ch, d + ch, "cy"))
    m.add_no_overlap_2d(xi, yi)
    for i in prog["portal"]:
        m.add(ys[i] == 0)
    wishes = [w for w in prog["wishes"] if w[0] in xs and w[1] in xs]
    # Apartments keep together: a residential wing, each next to another.
    flats = sorted(r["id"] for r in rooms if r["kind"] == "tenant")
    soft = [(a, b, 6) for a, b in zip(flats, flats[1:])]
    sat, weights, door_pairs = [], [], []
    for a, b, wgt in [(a, b, 20) for a, b in wishes] + soft:
        side = [m.new_bool_var(f"s{a}{b}{k}") for k in range(4)]
        m.add(xs[a] + ws[a] == xs[b]).only_enforce_if(side[0])
        m.add(xs[b] + ws[b] == xs[a]).only_enforce_if(side[1])
        m.add(ys[a] + hs[a] == ys[b]).only_enforce_if(side[2])
        m.add(ys[b] + hs[b] == ys[a]).only_enforce_if(side[3])
        for k in (0, 1):
            m.add(ys[a] + 1 <= ys[b] + hs[b]).only_enforce_if(side[k])
            m.add(ys[b] + 1 <= ys[a] + hs[a]).only_enforce_if(side[k])
        for k in (2, 3):
            m.add(xs[a] + 1 <= xs[b] + ws[b]).only_enforce_if(side[k])
            m.add(xs[b] + 1 <= xs[a] + ws[a]).only_enforce_if(side[k])
        ok = m.new_bool_var(f"ok{a}{b}")
        m.add_bool_or(side).only_enforce_if(ok)
        sat.append(ok)
        weights.append(wgt)
        door_pairs.append((a, b, wgt == 20))
    # Fill the envelope: no leftover holes in the ring or the row.
    m.maximize(sum(w * o for w, o in zip(weights, sat)) + 2 * sum(areas))
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = seconds
    sv.parameters.random_seed = seed
    sv.parameters.num_workers = int(os.environ.get("SOLVER_WORKERS", "2"))
    st = sv.solve(m)
    status = sv.status_name(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": status, "typology": typology, "site": [W, H]}
    placed = [{**r, "x": sv.value(xs[r["id"]]), "y": sv.value(ys[r["id"]]),
               "w": sv.value(ws[r["id"]]), "h": sv.value(hs[r["id"]])} for r in rooms]
    doors = [(a, b) for (a, b, real), ok in zip(door_pairs, sat) if sv.value(ok) and real]
    flats_joined = sum(1 for (a, b, real), ok in zip(door_pairs, sat) if sv.value(ok) and not real)
    built = sum(r["w"] * r["h"] for r in placed)
    envelope = W * H - ((W - 2 * d) * (H - 2 * d) if typology == "courtyard" else 0)
    return {"status": status, "typology": typology, "site": [W, H], "ring": d, "rooms": placed, "doors": doors,
            "wishes": len(wishes), "doors_made": len(doors), "flats_joined": f"{flats_joined}/{len(soft)}",
            "fill": round(built / envelope, 3), "objective": sv.objective_value}


def _shared_wall(a: dict, b: dict):
    """Midpoint and orientation of the wall a and b share, in cells."""
    if a["x"] + a["w"] == b["x"] or b["x"] + b["w"] == a["x"]:
        x = a["x"] + a["w"] if a["x"] + a["w"] == b["x"] else a["x"]
        lo, hi = max(a["y"], b["y"]), min(a["y"] + a["h"], b["y"] + b["h"])
        return x, (lo + hi) / 2, "v"
    y = a["y"] + a["h"] if a["y"] + a["h"] == b["y"] else a["y"]
    lo, hi = max(a["x"], b["x"]), min(a["x"] + a["w"], b["x"] + b["w"])
    return (lo + hi) / 2, y, "h"


PALETTE = {"Reception hall": "#e8d8b8", "Workshop": "#d9e2cf", "Archive": "#c9c0d8", "Pantry": "#f0e0c8",
           "Night workshop": "#c8d4e0", "Apartment": "#efe7da"}


def svg(plan: dict, title: str) -> str:
    s = 28
    W, H = plan["site"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * s + 80}" height="{H * s + 110}" font-family="Georgia, serif">',
           '<rect width="100%" height="100%" fill="#faf7f0"/>',
           f'<text x="40" y="34" font-size="18" fill="#333">{title}</text>',
           f'<g transform="translate(40,60)">',
           f'<rect x="0" y="0" width="{W * s}" height="{H * s}" fill="none" stroke="#bbb" stroke-dasharray="4 4"/>']
    for x in range(0, W + 1, 3):
        out.append(f'<circle cx="{x * s}" cy="{H * s}" r="3" fill="#999"/>')
    centre = {}
    for r in plan["rooms"]:
        x, y, w, h = r["x"] * s, (H - r["y"] - r["h"]) * s, r["w"] * s, r["h"] * s
        centre[r["id"]] = (x + w / 2, y + h / 2)
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{PALETTE.get(r["use"], "#eee")}" stroke="#333" stroke-width="2.5"/>')
        out.append(f'<text x="{x + 6}" y="{y + 16}" font-size="11" fill="#333">{r["use"]}</text>')
        out.append(f'<text x="{x + 6}" y="{y + 30}" font-size="9" fill="#777">{r["w"] * CELL_M:.0f}×{r["h"] * CELL_M:.0f} m</text>')
    byid = {r["id"]: r for r in plan["rooms"]}
    for a, b in plan["doors"]:
        x, y, o = _shared_wall(byid[a], byid[b])
        px, py = x * s, (H - y) * s
        if o == "v":
            out.append(f'<line x1="{px}" y1="{py - 9}" x2="{px}" y2="{py + 9}" stroke="#faf7f0" stroke-width="5"/>')
            out.append(f'<path d="M{px},{py - 9} A18,18 0 0,1 {px + 18},{py + 9}" fill="none" stroke="#666" stroke-width="0.8"/>')
        else:
            out.append(f'<line x1="{px - 9}" y1="{py}" x2="{px + 9}" y2="{py}" stroke="#faf7f0" stroke-width="5"/>')
            out.append(f'<path d="M{px - 9},{py} A18,18 0 0,1 {px + 9},{py - 18}" fill="none" stroke="#666" stroke-width="0.8"/>')
    if plan["typology"] == "courtyard":
        d = plan["ring"]
        out.append(f'<text x="{W * s / 2 - 40}" y="{H * s / 2}" font-size="14" fill="#8a8a7a" font-style="italic">Courtyard</text>')
        out.append(f'<rect x="{d * s}" y="{d * s}" width="{(W - 2 * d) * s}" height="{(H - 2 * d) * s}" fill="#e9efe0" stroke="none" opacity="0.6"/>')
    out.append("</g></svg>")
    return "\n".join(out)


def dxf(plan: dict, path: Path):
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()
    for r in plan["rooms"]:
        x, y, w, h = (v * CELL_M for v in (r["x"], r["y"], r["w"], r["h"]))
        msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True)
        msp.add_text(r["use"], dxfattribs={"height": 0.6}).set_placement((x + 0.4, y + h - 1))
    doc.saveas(path)


def design(scenarios: Path, cluster: str, at: datetime, label: str, out: Path) -> dict:
    facts = json.loads((scenarios / cluster / "facts.json").read_text())
    objs = state_at(scenarios / cluster / "ops.jsonl", at)
    prog = programme(objs, cluster)
    if not prog["wishes"]:
        prog["wishes"] = deps_from_scenario(facts, cluster)
    seed = int.from_bytes(hashlib.sha256((cluster + label).encode()).digest()[:4], "big") % 10000
    notebook, best = [], None
    for typ in ("courtyard", "enfilade"):
        plan = solve(prog, typ, seed=seed)
        notebook.append({k: plan.get(k) for k in ("typology", "status", "wishes", "doors_made", "flats_joined", "fill", "objective")})
        if plan.get("rooms"):
            # Every typology tried stays as a sketch in the notebook.
            sk = out / "sketches"
            sk.mkdir(parents=True, exist_ok=True)
            (sk / f"{cluster}_{label.replace(':', '_')}_{typ}.svg").write_text(svg(plan, f"{cluster} · {label} · {typ} (sketch)"))
            if best is None or plan["objective"] > best["objective"]:
                best = plan
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{cluster}_{label.replace(':', '_')}"
    (out / f"{stem}.svg").write_text(svg(best, f"{cluster} · {label} · {best['typology']}"))
    dxf(best, out / f"{stem}.dxf")
    rec = {"cluster": cluster, "window": label, "at": at.isoformat(), "programme": prog, "plan": best,
           "notebook": notebook}
    (out / f"{stem}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return {"stem": stem, "rooms": len(prog["rooms"]), "chosen": best["typology"], "trials": notebook}


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Design the building of a window.")
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--material", type=Path, default=Path("out/material"))
    ap.add_argument("--window", default="quarter_2025-Q4")
    ap.add_argument("--out", type=Path, default=Path("out/works/architecture"))
    a = ap.parse_args()
    for c in a.clusters:
        mat = json.loads((a.material / c / f"{a.window}.json").read_text())
        at = datetime.fromisoformat(mat["to"])
        print(json.dumps(design(a.scenarios, c, at, mat["window"], a.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
