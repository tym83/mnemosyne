"""The workshop as state of the cluster.

Everything the artist owns lives as ordinary Kubernetes objects in its
namespace, so the record loop backs it up with the rest of the cluster
and a restored cluster wakes the artist with it:

* Atelier — the biography: period, temperament, teachers and their weights;
* Leitmotif — one per character: archetype, colour, room, accord, theme;
* Opus — a finished or unfinished work: window, art, files, status;
* Notebook — the search behind a work: brief, choices, rejected trials,
  the artist's diary, verdicts;
* Sketch — a scrap: a melodic idea, a thumbnail, a trial formula.

Files (scores, images, plans, texts) live in a content-addressed store;
objects refer to them by sha256, never by a path that could move.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml

GROUP = "art.scheherazade.dev"
VERSION = "v1alpha1"
NS = "scheherazade"

KINDS = {
    "Atelier": "ateliers",
    "Leitmotif": "leitmotifs",
    "Opus": "opera",
    "Notebook": "notebooks",
    "Sketch": "sketches",
}


def crds() -> list[dict]:
    """Open schemas: the workshop's records are documents, not settings."""
    out = []
    for kind, plural in KINDS.items():
        out.append({
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"{plural}.{GROUP}"},
            "spec": {
                "group": GROUP,
                "scope": "Namespaced",
                "names": {"kind": kind, "plural": plural, "singular": kind.lower(), "listKind": kind + "List"},
                "versions": [{
                    "name": VERSION, "served": True, "storage": True,
                    "schema": {"openAPIV3Schema": {"type": "object", "properties": {
                        "spec": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
                        "status": {"type": "object", "x-kubernetes-preserve-unknown-fields": True},
                    }}},
                    "subresources": {"status": {}},
                }],
            },
        })
    return out


def obj(kind: str, name: str, spec: dict, status: dict | None = None, labels: dict | None = None) -> dict:
    o = {"apiVersion": f"{GROUP}/{VERSION}", "kind": kind,
         "metadata": {"name": name, "namespace": NS, "labels": labels or {}}, "spec": spec}
    if status:
        o["status"] = status
    return o


def slug(s: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in s.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:60]


class Store:
    """Content-addressed files of the works."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, path: Path) -> dict:
        data = path.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        dst = self.root / h[:2] / h
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists():
            shutil.copyfile(path, dst)
        return {"sha256": h, "name": path.name, "bytes": len(data)}


class Atelier:
    """Collects the workshop state of one cluster and writes it as manifests."""

    def __init__(self, cluster: str, out: Path):
        self.cluster = cluster
        self.out = out / cluster
        self.store = Store(out / "store")
        self.objects: list[dict] = []

    def biography(self, born: datetime, period: str, temperament: str, teachers: dict):
        self.objects.append(obj("Atelier", "artist", {
            "cluster": self.cluster, "born": born.isoformat(), "period": period,
            "temperament": temperament, "teachers": teachers,
        }))

    def leitmotif(self, character: dict, colour: str, room: str, accord: str, theme: dict | None = None):
        cid = character["id"]
        self.objects.append(obj("Leitmotif", slug(cid), {
            "character": cid, "archetype": character.get("role"), "temperament": character.get("temperament"),
            "colour": colour, "room": room, "accord": accord, "theme": theme or {},
        }))

    def opus(self, art: str, window: str, title: str, files: list[Path], made: datetime, status: str,
             notebook: dict, sketches: list[dict] | None = None, extra: dict | None = None) -> str:
        name = slug(f"{art}-{window}")
        refs = [self.store.put(f) for f in files if f.exists()]
        self.objects.append(obj("Opus", name, {
            "art": art, "window": window, "title": title, "files": refs, **(extra or {}),
        }, status={"phase": status, "madeAt": made.isoformat()}, labels={"art": art}))
        self.objects.append(obj("Notebook", name, {"opus": name, **notebook}))
        for i, sk in enumerate(sketches or []):
            files_ = [self.store.put(Path(f)) for f in sk.pop("files", []) if Path(f).exists()]
            self.objects.append(obj("Sketch", f"{name}-{i:03d}", {"opus": name, **sk, "files": files_}))
        return name

    def write(self):
        self.out.mkdir(parents=True, exist_ok=True)
        ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NS}}
        (self.out / "crds.yaml").write_text(yaml.safe_dump_all(crds(), sort_keys=False))
        (self.out / "state.yaml").write_text(yaml.safe_dump_all([ns] + self.objects, sort_keys=False, allow_unicode=True))
        counts = {}
        for o in self.objects:
            counts[o["kind"]] = counts.get(o["kind"], 0) + 1
        return counts
