"""The workshop as state of the cluster.

Everything the artist owns lives as ordinary Kubernetes objects in its
namespace, so the record loop backs it up with the rest of the cluster
and a restored cluster wakes the artist with it:

* Atelier — the lineage, its resumable fate engine and growing book;
* Artist — a life, catalogue, periods, teachers and creative state;
* Biography — the chronicler's chapters linked to works and drafts;
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

GROUP = "mnemosyne.art"
GROUP_ALIASES = {GROUP: GROUP, "art.scheherazade.dev": GROUP}
VERSION = "v1alpha1"
NS = "mnemosyne"

KINDS = {
    "Atelier": "ateliers",
    "Leitmotif": "leitmotifs",
    "Opus": "opera",
    "Notebook": "notebooks",
    "Sketch": "sketches",
    "Artist": "artists",
    "Biography": "biographies",
    "Review": "reviews",
    "AudienceLog": "audiencelogs",
    "Edition": "editions",
}


def is_atelier_object(record: dict) -> bool:
    """Recognize current and pre-rename records without rewriting backup data."""
    group, _, version = record.get('apiVersion', '').partition('/')
    return GROUP_ALIASES.get(group) == GROUP and version == VERSION and record.get('kind') in KINDS


def crds() -> list[dict]:
    """Structural schemas: validate runtime settings, retain artistic documents."""
    from .operator.schema import schema
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
                    "schema": {"openAPIV3Schema": schema(kind)},
                    "additionalPrinterColumns": [
                        {"name": "Phase", "type": "string", "jsonPath": ".status.phase"},
                        {"name": "Art", "type": "string", "jsonPath": ".spec.art"},
                        {"name": "Age", "type": "date", "jsonPath": ".metadata.creationTimestamp"},
                    ],
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
        """Legacy single-portrait export; new lives use lineage()."""
        self.objects.append(obj("Atelier", "artist", {
            "cluster": self.cluster, "born": born.isoformat(), "period": period,
            "temperament": temperament, "teachers": teachers,
        }))

    def lineage(self, life):
        """Persist the complete resumable lineage and its book as ordinary state.

        Artist and Biography are first-class objects; Opus/Notebook/Sketch
        references resolve even for synthetic, unfinished and refused works.
        """
        from dataclasses import asdict

        if life.cluster != self.cluster:
            raise ValueError('lineage belongs to another atelier')
        state = life.state()
        self.objects.append(obj('Atelier', slug(self.cluster), {
            'lineage': {k: v for k, v in state.items() if k not in ('artists', 'biographies')},
            'artists': [a.id for a in life.artists],
            'book': f'{self.cluster}-lives',
        }))
        book_path = self.out / 'lives.md'
        self.out.mkdir(parents=True, exist_ok=True)
        book_path.write_text(life.markdown())
        book_ref = self.store.put(book_path)
        self.objects.append(obj('Opus', f'{self.cluster}-lives', {
            'art': 'literature', 'title': 'Lives', 'files': [book_ref],
            'biographies': list(life.biographies), 'carrier': 'ordinary-state-until-literature-channel',
        }, status={'phase': 'growing'}))
        for review in life.reception.reviews:
            self.objects.append(obj('Review', f'{self.cluster}-{review["id"]}', review))
        for edition in life.reception.releases:
            self.objects.append(obj('Edition', f'{self.cluster}-{edition["id"]}', edition))
        for log in life.reception.logs:
            self.objects.append(obj('AudienceLog', f'{self.cluster}-{log["id"]}', {
                **log, 'carrier': 'audience-timing-v1', 'gross_bytes': len(log['timestamps_ms']),
            }))
        for a in life.artists:
            self.objects.append(obj('Artist', a.id, asdict(a)))
            self.objects.append(obj('Biography', a.id, {
                **asdict(life.biographies[a.id]), 'book': f'{self.cluster}-lives',
            }))
            self.objects.append(obj('Notebook', a.id, {'artist': a.id, 'entries': a.notebook}))
            for w in a.catalogue:
                self.objects.append(obj('Opus', w['id'], {'artist': a.id, **w},
                                        status={'phase': w['verdict']}))
                self.objects.append(obj('Notebook', w['notebook'], {
                    'opus': w['id'], 'artist': a.id, 'idea': w['idea'],
                    'idea_seed': w['idea_seed'], 'method': w['method'],
                    'influences': w['influences'], 'verdict': w['verdict'],
                    'halftones': w['halftones'], 'drafts': [w['draft']],
                    'process': w['process'],
                }))
                self.objects.append(obj('Sketch', w['draft'], {
                    'opus': w['id'], 'synthetic': w['synthetic'], 'feature': w['feature'],
                }))
                composer = w['process'].get('composer')
                if composer:
                    for sketch in composer.get('sketches', []):
                        self.objects.append(obj('Sketch', sketch['id'], {
                            **sketch, 'files': sketch.get('file_refs', []),
                            'artist': a.id, 'opus': w['id'], 'notebook': w['notebook'],
                        }))
                    for record in self.objects:
                        if record['kind'] == 'Notebook' and record['metadata']['name'] == w['notebook']:
                            record['spec']['composer'] = composer
                            record['spec']['drafts'] = [s['id'] for s in composer.get('sketches', [])]
                        if record['kind'] == 'Sketch' and record['metadata']['name'] == w['draft']:
                            record['spec']['source'] = composer.get('final')
                        if record['kind'] == 'Opus' and record['metadata']['name'] == w['id']:
                            final = next((s for s in composer.get('sketches', [])
                                          if s['id'] == composer.get('final')), {})
                            record['spec'].update(art='music', files=final.get('file_refs', []),
                                                  final_sketch=final.get('id'))


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
