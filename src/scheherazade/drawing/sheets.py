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
import os
import subprocess
from pathlib import Path

from pydantic import BaseModel

from ..artist import SelfPortrait, Statement, halftones, inner_life, theory
from ..literature import Writer

KIT = Path(__file__).with_name("bpy_kit.py")
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
    style: str  # ink | wash | chiaroscuro | color


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


def draw(script: str, local_png: Path, size=(1500, 1000, 64)) -> str:
    """Render one sheet in the workshop; returns Blender's complaint or ''."""
    name = f"{local_png.parent.name}_{local_png.stem}"
    local_py = local_png.with_suffix(".py")
    local_py.write_text(script)
    kube("exec", POD, "--", "mkdir", "-p", f"{REMOTE}/kit")
    for f in (KIT, RUNNER):
        kube("cp", str(f), f"{POD}:{REMOTE}/kit/{f.name}")
    kube("cp", str(local_py), f"{POD}:{REMOTE}/{name}.py")
    r = kube("exec", POD, "--", "sh", "-c",
             f"rm -f {REMOTE}/{name}.png; /work/blender/blender -b -t 24 -P {REMOTE}/kit/run_sheet.py -- "
             f"{REMOTE}/{name}.py {REMOTE}/{name}.png {size[0]} {size[1]} {size[2]} 2>&1 | tail -40", timeout=3600)
    got = kube("cp", f"{POD}:{REMOTE}/{name}.png", str(local_png))
    if got.returncode or not local_png.exists():
        lines = [x for x in r.stdout.splitlines() if not x.startswith("Fra:")]
        return "\n".join(lines[-25:]) or "no image"
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
    me = (f"Ты — {p.name}. {p.what_i_am_as_artist}\n\nТвоя идея: {st.idea}\n\nСверхзадача: {st.superobjective}\n\n"
          f"Твой метод «{method.get('name', '')}»: {'; '.join(method.get('manifesto', []))}\n\nОттенки (полутона) "
          f"этой работы: {tone}\n\nИскусство: {art}. Не упоминай технику, компьютеры, серверы.")
    critique = rec["interrogation"][-1]["interrogation"]
    plan = w.ask(me, "Спланируй путь работы листами, как это делали Пиранези, Булле, Леонидов, Бродский и Уткин: "
                 "2–3 быстрые почеркушки (композиция, точка зрения, свет — пробуй разное, спорь с собой), 1–2 этюда "
                 "(разрез, фасад, аксонометрия — то, что нужно именно этой идее), и один итоговый лист. Для каждого "
                 "листа: что он показывает, зачем он на пути, вид, свет, стиль (ink, wash, chiaroscuro, color). "
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
        for k in range(1, drafts + 1):
            ask = (f"Лист {n} из {len(plan.sheets)} ({sh.kind}): «{sh.title}». {sh.what_it_shows}\nЗачем: "
                   f"{sh.why_this_sheet}\nВид: {sh.view}\nСвет: {sh.light}\nСтиль: {sh.style}\n\nПуть: "
                   f"{plan.order_of_search}\nУже сделано: {'; '.join(before) or 'ничего'}")
            if script:
                ask += f"\n\nТвой прошлый черновик:\n```python\n{script}\n```\n{note}"
            d = w.ask(hand, ask, Drawing, f"sheet{n}:draft{k}")
            png = out / f"sheet{n:02d}_draft{k}.png"
            err = draw(d.script, png)
            script = d.script
            if err:
                hist.append({"draft": k, "script": d.script, "error": err})
                note = f"Лист не нарисовался, вот что сказал станок:\n{err}\nИсправь сценарий."
                continue
            look = w.ask(me, f"Это твой черновик листа «{sh.title}» ({sh.kind}). Смотри на то, что нарисовано, а не "
                         f"на то, что задумано. Чего хотел: {sh.what_it_shows}. Что работает, что нет, какую "
                         "поправку назвать словами. Оставить лист (leave_it) — когда дальнейшая правка станет порчей."
                         "\n\nМерила мастеров:\n" + theory("drafts", "test"), Look, f"sheet{n}:look{k}", images=[png])
            hist.append({"draft": k, "script": d.script, "changed": d.what_i_changed, "image": png.name,
                         "look": look.model_dump()})
            if look.leave_it:
                break
            note = (f"Ты посмотрел на него и увидел: {look.i_see}\nНе работает: {'; '.join(look.fails)}\n"
                    f"Поправка: {look.correction}")
        last = next((h for h in reversed(hist) if "image" in h), None)
        if last and sh.kind == "plate":
            final = out / f"sheet{n:02d}_plate.png"
            if not draw(last["script"], final, (2700, 1800, 256)):
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
