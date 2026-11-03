"""Paper architecture: from an idea to sheets, through sketches and drafts.

The artist plans the path of a work as a set of sheets — quick thumbnails
that try a composition, a viewpoint, a light; studies (a section, an
elevation, an axonometry); and the final plate. Each sheet is drawn by the
artist's own hand as a short scene script, rendered in Blender in the
workshop, and then looked at: what the eye sees, what works, what fails,
what to correct (Gombrich: schema and correction). The artist decides when
to leave a sheet (Valéry). Every draft is kept: the path is part of the
work and of the backup.

    WRITER=codex uv run python -m scheherazade.drawing.sheets shop bank
"""

from __future__ import annotations

import ast
import json
import hashlib
import uuid
import os
import subprocess
import shutil
from pathlib import Path

from pydantic import BaseModel
from typing import Literal

from .etch import difference

from ..artist import SelfPortrait, Statement, halftones, inner_life, theory
from ..literature import Writer

KIT = Path(__file__).with_name("bpy_kit.py")
ETCHER = Path(__file__).with_name("etch.py")
EXEMPLARS = Path(__file__).resolve().parents[3] / "atlas/architecture/exemplars"
RUNNER = Path(__file__).with_name("run_sheet.py")
POD = os.environ.get("STUDIO_POD", "studio-1")
REMOTE = "/work/sheets"
KUBE = ["kubectl", "--kubeconfig", str(Path("~/workshop.txt").expanduser()), "--context", "admin@workshop",
        "-n", "tenant-scheherazade"]


class Sheet(BaseModel):
    kind: str  # sketch | study | plate
    title: str
    what_it_shows: str
    why_this_sheet: str  # what this sheet must find out or say on the way to the plate
    view: str  # section, elevation, perspective, axonometry, plan — and from where
    light: str
    style: Literal["etching", "aquatint", "ink_line"]


class Path_(BaseModel):
    sheets: list[Sheet]
    order_of_search: str  # how the sheets lead one to another


class Drawing(BaseModel):
    script: str
    what_i_changed: str


class Look(BaseModel):
    i_see: str  # what is actually on the sheet, not what was meant
    works: list[str]
    fails: list[str]
    correction: str  # the next correction, named in words
    weaker_than_master: str  # concrete visible weaknesses against the attached exemplar
    composition_settled: bool
    correction_scale: Literal["viewpoint", "scale", "light", "detail"]
    leave_it: bool  # Valéry: the sheet is left, not finished


class Verdict(BaseModel):
    verdict: str  # "accept" or "rewrite"
    what_the_plate_does: str
    cliches_found: list[str]
    what_is_missing: str


def kit_reference() -> str:
    """The kit's words with their meaning, read from the source."""
    tree = ast.parse(KIT.read_text())
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            args = ast.unparse(n.args)
            doc = (ast.get_docstring(n) or "").strip()
            out.append(f"{n.name}({args})" + (f"\n    {doc}" if doc else ""))
    keys = {n.targets[0].id: ", ".join(k.value for k in n.value.keys) for n in tree.body
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict) and isinstance(n.targets[0], ast.Name)}
    poses, palette = keys["POSES"], keys["PALETTE"]
    return "\n".join(out) + f"\n\nПозы фигур: {poses}.\nМатериалы: {palette}."


def kube(*args, **kw):
    return subprocess.run([*KUBE, *args], capture_output=True, text=True, **kw)


def draw(script: str, local_png: Path, size=(2700, 1800, 96), *, title="Этюд", artist="", number=1) -> str:
    """Render and print in the pod; preserve sources and fingerprint all inputs."""
    local_png.parent.mkdir(parents=True, exist_ok=True)
    local_py = local_png.with_suffix(".py")
    state = local_png.with_suffix(".render-state")
    manifest = local_png.with_suffix(".render.json")
    fingerprint = hashlib.sha256(json.dumps([script, size, title, artist, number,
        *[f.read_text() for f in (KIT, RUNNER, ETCHER)]], ensure_ascii=False).encode()).hexdigest()
    if (local_png.exists() and state.exists() and state.read_text() == "done"
            and manifest.exists() and json.loads(manifest.read_text()).get("fingerprint") == fingerprint):
        return ""
    existing = list(local_png.parent.glob(local_png.stem + ".*")) + list(local_png.parent.glob(local_png.stem + "_*.png"))
    if existing:
        archive = local_png.parent / "history" / f"{local_png.stem}_{uuid.uuid4().hex}"
        archive.mkdir(parents=True)
        for file in existing:
            if file.is_file():
                shutil.copy2(file, archive / file.name)
    state.write_text("pending")
    local_py.write_text(script)
    # Unique directories preserve earlier renders and prevent stale-output reuse.
    remote = f"{REMOTE}/{uuid.uuid4().hex}"

    def checked(*args, **kwargs):
        r = kube(*args, **kwargs)
        if r.returncode:
            raise RuntimeError((r.stdout + (r.stderr or ""))[-6000:] or "workshop command failed")
        return r

    try:
        checked("exec", POD, "--", "mkdir", "-p", remote)
        for f in (KIT, RUNNER, ETCHER, local_py):
            checked("cp", str(f), f"{POD}:{remote}/{f.name}")
        r = checked("exec", POD, "--", "/work/blender/blender", "-b", "-t", "24",
                    "--python-exit-code", "1", "-P", f"{remote}/run_sheet.py", "--",
                    f"{remote}/{local_py.name}", f"{remote}/source.png", *map(str, size), timeout=3600)
        local_png.with_suffix(".render.log").write_text(r.stdout + (r.stderr or ""))
        checked("exec", POD, "--", "/work/venv/bin/python", f"{remote}/etch.py",
                f"{remote}/source.png", f"{remote}/plate.png", "--title", title,
                "--artist", artist, "--number", str(number), timeout=180)
        for remote_name, local_name in (("source.png", local_png.with_name(local_png.stem + "_source.png")),
                                        ("source_normals.png", local_png.with_name(local_png.stem + "_normals.png")),
                                        ("plate.png", local_png)):
            checked("cp", f"{POD}:{remote}/{remote_name}", str(local_name))
        if not local_png.exists():
            raise RuntimeError("no image")
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        local_png.with_suffix(".render.log").write_text(str(error))
        return str(error)
    manifest.write_text(json.dumps({"fingerprint": fingerprint, "remote": remote}, indent=2))
    state.write_text("done")
    return ""


def work(rec: dict, out: Path, backend: str | None = None, drafts: int = 4) -> dict:
    nb = rec.setdefault("notebook", [])
    p, st = SelfPortrait(**rec["portrait"]), Statement(**rec["statement"])
    art = "архитектура как искусство: визионерская, бумажная архитектура; лист — это и есть произведение"
    if "halftones" not in rec:
        inner = inner_life(Path("out/scenarios"), rec["cluster"], __import__("datetime").datetime.fromisoformat(
            "2025-12-31T23:00:00+00:00"))
        rec["inner_life"] = inner
        rec["halftones"] = halftones(p, st, st.idea, inner, nb, backend).model_dump()
    tone = json.dumps(rec["halftones"], ensure_ascii=False)
    method = rec.get("method", {})
    w = Writer(nb, backend=backend)
    language = ("Язык листа — гравированная доска бумажной архитектуры Пиранези, Булле, Бродского–Уткина. "
                "Архитектура господствует. Люди — маленькие безликие силуэты, не выше 1/15 кадра; "
                "никаких лиц, персонажей в центре и бытовых сценок. Никаких слов и текстовых объектов "
                "в сцене: название, имя и номер будут в картуше под изображением. Предпочитай "
                "ортографический вид и один косой свет. Не изображай события кластера буквально. "
                "Выбирай etching (штрих), aquatint (штрих и зернистая отмывка), ink_line (перо).")
    exemplars = sorted(EXEMPLARS.glob("*.jpg"))
    if not exemplars:
        raise FileNotFoundError(f"No public-domain exemplars in {EXEMPLARS}")
    me = (f"Ты — {p.name}. {p.what_i_am_as_artist}\n\nТвоя идея: {st.idea}\n\nСверхзадача: {st.superobjective}\n\n"
          f"Твой метод «{method.get('name', '')}»: {'; '.join(method.get('manifesto', []))}\n\nОттенки (полутона) "
          f"этой работы: {tone}\n\nИскусство: {art}. Не упоминай технику, компьютеры, серверы." + "\n" + language)
    critique = rec["interrogation"][-1]["interrogation"]
    plan = w.ask(me, "Спланируй путь работы листами, как это делали Пиранези, Булле, Леонидов, Бродский и Уткин: "
                 "2–3 быстрые почеркушки (композиция, точка зрения, свет — пробуй разное, спорь с собой), 1–2 этюда "
                 "(разрез, фасад, аксонометрия — то, что нужно именно этой идее), и один итоговый лист. Для каждого "
                 "листа: что он показывает, зачем он на пути, вид, свет, стиль (etching, aquatint, ink_line). "
                 "Помни, что Шахрияр сказал о замысле, и исправь это в листах, а не словами:\n"
                 f"Штампы: {'; '.join(critique['cliches_found'])}\nСлабое: {'; '.join(critique['weak_answers'])}\n\n"
                 "Что говорили мастера:\n" + theory("drafts", "operator") + "\n" + theory("concept", "operator"),
                 Path_, "sheets-plan")
    rec["sheets_plan"] = plan.model_dump()
    hand = (me + "\n\nТы рисуешь лист сам: пишешь короткий сценарий сцены на Python словами своего набора инструментов "
            "(они уже в области видимости; можно и bpy напрямую). Первая строка — reset(style). Обязательно камера "
            "и свет. Масштаб настоящий, в метрах; фигуры-стаффаж для масштаба. render() не вызывай — лист нарисуют "
            "за тебя. Набор:\n\n" + kit_reference())
    sheets, before = [], []
    for n, sh in enumerate(plan.sheets, 1):
        hist, script, note = [], None, ""
        previous_png = None
        exemplar = exemplars[(n - 1) % len(exemplars)]
        for k in range(1, drafts + 1):
            ask = (f"Лист {n} из {len(plan.sheets)} ({sh.kind}): «{sh.title}». {sh.what_it_shows}\nЗачем: "
                   f"{sh.why_this_sheet}\nВид: {sh.view}\nСвет: {sh.light}\nСтиль: {sh.style}\n\nПуть: "
                   f"{plan.order_of_search}\nУже сделано: {'; '.join(before) or 'ничего'}")
            if script:
                ask += f"\n\nТвой прошлый черновик:\n```python\n{script}\n```\n{note}"
            d = w.ask(hand, ask, Drawing, f"sheet{n}:draft{k}")
            png = out / f"sheet{n:02d}_draft{k}.png"
            err = draw(d.script, png, title=sh.title, artist=p.name, number=n)
            script = d.script
            if err:
                hist.append({"draft": k, "script": d.script, "error": err})
                note = f"Лист не нарисовался, вот что сказал станок:\n{err}\nИсправь сценарий."
                continue
            delta = difference(previous_png, png) if previous_png else None
            unchanged = bool(delta and delta["barely_changed"])
            warning = ("Черновик почти не изменился: " + json.dumps(delta) +
                       ". Следующая правка обязана заметно изменить точку зрения, масштаб или свет.") if unchanged else ""
            look = w.ask(me, f"Это твой черновик листа «{sh.title}» ({sh.kind}). Смотри на то, что нарисовано, а не "
                         f"на то, что задумано. Чего хотел: {sh.what_it_shows}. Что работает, что нет, какую "
                         "поправку назвать словами. Первое изображение — твой лист, второе — образец мастера. "
                         f"Образец: {exemplar.name}. В weaker_than_master прямо назови, где твой лист слабее мастера "
                         "по пространству, иерархии, свету и штриху. Укажи composition_settled. Пока композиция "
                         "не найдена, correction_scale — только viewpoint, scale или light, не detail; "
                         "назови конкретное крупное изменение. " + warning + " Оставить лист (leave_it) — когда дальнейшая правка станет порчей."
                         "\n\nМерила мастеров:\n" + theory("drafts", "test"), Look, f"sheet{n}:look{k}", images=[png, exemplar])
            if not look.composition_settled:
                look.leave_it = False
                if look.correction_scale == "detail":
                    look.correction = "Сначала измени точку зрения, масштаб или свет. " + look.correction
            if unchanged:
                look.leave_it = False
            previous_png = png
            hist.append({"draft": k, "script": d.script, "changed": d.what_i_changed, "image": png.name,
                         "look": look.model_dump(), "exemplar": exemplar.name, "difference": delta})
            if look.leave_it:
                break
            note = (f"Ты посмотрел на него и увидел: {look.i_see}\nНе работает: {'; '.join(look.fails)}\n"
                    f"Слабее мастера: {look.weaker_than_master}\nПоправка: {look.correction}\n{warning}"
                    + ("\nКомпозиция не найдена: меняй точку зрения, масштаб или свет, не детали."
                       if not look.composition_settled else ""))
        last = next((h for h in reversed(hist) if "image" in h), None)
        if last and sh.kind == "plate":
            final = out / f"sheet{n:02d}_plate.png"
            if not draw(last["script"], final, (2700, 1800, 256), title=sh.title, artist=p.name, number=n):
                last["plate"] = final.name
        sheets.append({"sheet": sh.model_dump(), "drafts": hist})
        before.append(f"{sh.title}: " + (last["look"]["i_see"] if last else "не нарисовался"))
    rec["sheets"] = sheets
    plates = [out / h["plate"] for s in sheets for h in s["drafts"] if h.get("plate")]
    if plates:
        critic = ("Ты — Шахрияр, беспощадный критик. Перед тобой итоговый лист бумажной архитектуры и замысел "
                  "художника. Суди лист, а не слова: что он делает со зрителем, какие в нём штампы, чего не хватает. "
                  "accept или rewrite. Мерила:\n" + theory("judgement", "test"))
        v = w.ask(critic, f"Замысел: {st.idea}\nСверхзадача: {st.superobjective}", Verdict, "plate-judgement",
                  images=plates)
        rec["plate_verdict"] = v.model_dump()
    return rec


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    ap.add_argument("--dir", type=Path, default=Path("out/works/artist"))
    ap.add_argument("--out", type=Path, default=Path("out/works/architecture"))
    ap.add_argument("--drafts", type=int, default=4)
    a = ap.parse_args()
    for c in a.clusters:
        rec = json.loads((a.dir / f"{c}.json").read_text())
        out = a.out / c
        out.mkdir(parents=True, exist_ok=True)
        rec = work(rec, out, drafts=a.drafts)
        (a.dir / f"{c}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        (out / "sheets.json").write_text(json.dumps({k: rec[k] for k in ("sheets_plan", "sheets", "halftones")
                                                     if k in rec} | {"plate_verdict": rec.get("plate_verdict")},
                                                    ensure_ascii=False, indent=1))
        print(c, "sheets:", len(rec["sheets"]), "| verdict:", (rec.get("plate_verdict") or {}).get("verdict"))


if __name__ == "__main__":
    main()
