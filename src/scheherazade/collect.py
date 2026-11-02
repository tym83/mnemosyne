"""Gather the works of stage A into the workshop state and readable notebooks.

For each cluster the works on disk (perfumes, buildings, paintings, poems,
stories, music) become Opus, Notebook and Sketch objects with the moment
each was finished in the cluster's virtual time, plus a Leitmotif for
every character met. `--at` cuts the state at a moment: what the artist
had finished, and what was still on the easel.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .atelier import Atelier

# How long after its window closes a work is finished (virtual time):
# a day's nocturne by morning, a year's symphony in spring.
DELAY = {"day": timedelta(hours=8), "week": timedelta(days=2), "month": timedelta(days=7),
         "quarter": timedelta(days=21), "year": timedelta(days=75), "incident": timedelta(days=3)}

COLOURS = ["#b33b24", "#1c345c", "#d9a441", "#5b7f5a", "#7a4e8c", "#2f6f73", "#c8875e", "#4a4a52"]
ROOMS = {"web": "Reception hall", "api": "Workshop", "db": "Archive", "cache": "Pantry", "worker": "Night workshop"}
ACCORDS = {"web": "cut-stem", "api": "effort", "db": "old-paper", "cache": "sea-crossing", "worker": "cold-incense"}


def finished_at(material: dict) -> datetime:
    kind = material["window"].split(":")[0]
    return datetime.fromisoformat(material["to"]) + DELAY.get(kind, timedelta(days=1))


def _material(root: Path, cluster: str, window: str) -> dict:
    return json.loads((root / cluster / f"{window.replace(':', '_')}.json").read_text())


def notebook_md(title: str, art: str, window: str, nb: dict) -> str:
    """The notebook as something to read: the search, not a log."""
    lines = [f"# Тетрадь к работе «{title}»", "", f"Искусство: {art}. Окно истории: {window}.", ""]
    for k, v in nb.items():
        lines.append(f"## {k}")
        lines.append("")
        if isinstance(v, list):
            for item in v[:40]:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)[:400]}")
        else:
            lines.append(f"```\n{json.dumps(v, ensure_ascii=False, indent=1)[:4000]}\n```")
        lines.append("")
    return "\n".join(lines)


def collect(cluster: str, works: Path, material_root: Path, out: Path, at: datetime | None) -> dict:
    at_ = at or datetime(2027, 1, 1, tzinfo=timezone.utc)
    atl = Atelier(cluster, out)
    facts = json.loads((Path("out/scenarios") / cluster / "facts.json").read_text())
    atl.biography(born=datetime(2025, 1, 1, tzinfo=timezone.utc), period="apprenticeship",
                  temperament="eventful" if len(facts["incidents"]) > 10 else "orderly",
                  teachers={"music": "Chopin / Tchaikovsky" if cluster == "shop" else "Chopin / Haydn",
                            "painting": "Rothko, Hokusai", "literature": "Chekhov, Gogol, Leskov",
                            "architecture": "courtyard, enfilade"})
    chars = {}
    nbdir = out / cluster / "notebooks"
    nbdir.mkdir(parents=True, exist_ok=True)
    made = []
    # Perfumery
    for f in sorted((works / "perfumery").glob(f"{cluster}_*.json")):
        w = json.loads(f.read_text())
        mat = _material(material_root, cluster, w["window"])
        t = finished_at(mat)
        nb = {"Бриф": w["brief"], "Как раскрывается": w["unfolding"], "Проигравшие пробы": w["notebook"]["surpassed"]}
        title = " → ".join(a["accord"] for a in w["brief"]["arc"])
        made.append(("perfumery", w["window"], title, [f.with_suffix(".md")], t, nb, []))
        for c in mat["characters"]:
            chars[c["id"]] = c
    # Architecture
    for f in sorted((works / "architecture").glob(f"{cluster}_*.json")):
        w = json.loads(f.read_text())
        mat = _material(material_root, cluster, w["window"])
        nb = {"Программа": w["programme"], "Типологии, которые пробовали": w["notebook"]}
        made.append(("architecture", w["window"], f"Building, {w['plan']['typology']}",
                     [f.with_suffix(".svg"), f.with_suffix(".dxf")], finished_at(mat), nb, []))
    # Painting
    for f in sorted((works / "painting").glob(f"{cluster}_*.json")):
        w = json.loads(f.read_text())
        mat = json.loads(Path(w["material"]).read_text())
        stem = f.stem
        files = [p for p in (works / "painting").glob(f"{stem}*.png")]
        sketches = [{"what": "trial", **{k: v for k, v in s.items() if k != "file"}, "files": [s["file"]]}
                    for s in w.get("sketches", [])]
        nb = {k: v for k, v in w.items() if k not in ("sketches", "variants")}
        made.append(("painting", mat["window"], stem, files, finished_at(mat), nb, sketches))
    # Literature and poetry (when written)
    for f in sorted((works / "literature").glob(f"{cluster}_*.json")):
        w = json.loads(f.read_text())
        window = w.get("material") or f.stem.split("_", 1)[1].replace("_", ":", 1)
        try:
            mat = _material(material_root, cluster, window.replace("_jisei", ""))
        except FileNotFoundError:
            continue
        nb = {"Путь поиска": w.get("notebook", [])}
        made.append(("literature", mat["window"], w.get("title", f.stem), [f.with_suffix(".md")], finished_at(mat), nb, []))
    # Music (when assembled)
    for f in sorted((works / "music").glob(f"{cluster}_*/work.json")):
        w = json.loads(f.read_text())
        meta = json.loads((f.parent / "meta.json").read_text())
        mat = _material(material_root, cluster, meta["window"])
        files = [Path(p) for p in f.parent.glob("*.musicxml")] + [Path(p) for p in f.parent.glob("*.pdf")]
        nb = {"Выбор": json.loads((f.parent / "choice.json").read_text())} if (f.parent / "choice.json").exists() else {}
        made.append(("music", meta["window"], w.get("title", meta["window"]), files, finished_at(mat), nb, []))
    counts = {"finished": 0, "on-the-easel": 0}
    for art, window, title, files, t, nb, sketches in made:
        status = "finished" if t <= at_ else ("on-the-easel" if datetime.fromisoformat(
            _material(material_root, cluster, window)["from"]) <= at_ else None)
        if status is None:
            continue
        counts[status] += 1
        name = atl.opus(art, window, title, files if status == "finished" else [], t, status, nb, sketches)
        (nbdir / f"{name}.md").write_text(notebook_md(title, art, window, nb))
    for i, (cid, c) in enumerate(sorted(chars.items())):
        atl.leitmotif(c, COLOURS[i % len(COLOURS)], ROOMS.get(c["kind"], "Apartment"), ACCORDS.get(c["kind"], "skin"))
    return {"cluster": cluster, "at": at_.isoformat(), **counts, "objects": atl.write()}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    ap.add_argument("--works", type=Path, default=Path("out/works"))
    ap.add_argument("--material", type=Path, default=Path("out/material"))
    ap.add_argument("--out", type=Path, default=Path("out/atelier"))
    ap.add_argument("--at", default=None, help="cut the state at this moment, e.g. 2025-07-01T00:00:00+00:00")
    a = ap.parse_args()
    at = datetime.fromisoformat(a.at) if a.at else None
    for c in a.clusters:
        print(json.dumps(collect(c, a.works, a.material, a.out / (a.at[:10] if a.at else "end"), at), ensure_ascii=False))


if __name__ == "__main__":
    main()
