"""Death poems (jisei) of a day.

Every death in the cluster that day — replicas let go after a crowd, a
version replaced by a newer one, a restart, a household removed — gets a
three-line poem in the form of a haiku: 5–7–5 syllables, a seasonal word
of the date, an image of leaving. The model never hears what died: it
receives the season, how long the life was, and how it ended (quietly, in
a storm, replaced by a younger one). Code counts the syllables and checks
for technical words; a poem that fails is rewritten.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .literature import FORBIDDEN_WORDS, Writer

VOWELS = set("аеёиоуыэюяАЕЁИОУЫЭЮЯ")

SEASON = {
    12: "начало зимы", 1: "середина зимы", 2: "конец зимы", 3: "начало весны", 4: "середина весны",
    5: "конец весны", 6: "начало лета", 7: "середина лета", 8: "конец лета", 9: "начало осени",
    10: "середина осени", 11: "поздняя осень",
}


class Poem(BaseModel):
    lines: list[str]
    note: str  # the artist's note: which image and why


def syllables(line: str) -> int:
    return sum(1 for ch in line if ch in VOWELS)


def deaths(ops_path: Path, a: datetime, b: datetime, tz: str, limit: int = 12, incidents: list | None = None) -> list[dict]:
    """What died in the window, and how. Lifetimes come from the history."""
    born: dict = {}
    last_up: dict = {}
    out = []
    zone = ZoneInfo(tz)
    for line in ops_path.open():
        o = json.loads(line)
        t = datetime.fromisoformat(o["at"])
        if t >= b:
            break
        obj = o["object"]
        k = (obj["kind"], obj["metadata"].get("namespace", ""), obj["metadata"]["name"])
        prev = born.get(k)
        if t < a:
            if obj["kind"] == "Deployment" and prev and obj["spec"].get("replicas", 1) > prev["obj"]["spec"].get("replicas", 1):
                last_up[k] = t
            if o["op"] != "delete":
                born[k] = {"since": born.get(k, {}).get("since", t), "obj": obj}
            continue
        if obj["kind"] == "Deployment" and prev:
            r0 = prev["obj"]["spec"].get("replicas", 1)
            r1 = obj["spec"].get("replicas", 1)
            img0 = prev["obj"]["spec"]["template"]["spec"]["containers"][0]["image"]
            img1 = obj["spec"]["template"]["spec"]["containers"][0]["image"]
            ann0 = prev["obj"]["spec"]["template"]["metadata"].get("annotations", {})
            ann1 = obj["spec"]["template"]["metadata"].get("annotations", {})
            life_h = (t - prev["since"]).total_seconds() / 3600
            if r1 > r0:
                last_up[k] = t
            if r1 < r0:
                # The youngest go first: those that came with the last crowd.
                young = (t - last_up.get(k, prev["since"])).total_seconds() / 3600
                out.append({"at": t, "how": "отпущен тихо, когда схлынула толпа", "life_hours": young, "count": r0 - r1})
            if img1 != img0:
                how = "заменён прежним, старшим, после беды" if "rollback" in o["reason"] else "уступил место младшему"
                out.append({"at": t, "how": how, "life_hours": life_h, "count": r1})
            if ann1 != ann0:
                out.append({"at": t, "how": "оборван посреди бури и рождён заново", "life_hours": life_h, "count": r1})
        if obj["kind"] == "Namespace" and o["op"] == "delete":
            out.append({"at": t, "how": "дом опустел, все ушли", "life_hours": (t - prev["since"]).total_seconds() / 3600 if prev else 0, "count": 1})
        if o["op"] == "delete":
            born.pop(k, None)
        else:
            born[k] = {"since": prev["since"] if prev and o["op"] != "create" and not
                       (obj["kind"] == "Deployment" and prev["obj"]["spec"]["template"] != obj["spec"]["template"]) else t, "obj": obj}
    # Storms kill too: pods that fell during an incident and were reborn.
    for inc in incidents or []:
        st = datetime.fromisoformat(inc["start"])
        if a <= st < b:
            out.append({"at": st, "how": "пал в бурю, в самый разгар", "life_hours": 3.0,
                        "count": max(1, round(inc["severity"] * 6 * len(inc["affected"])))})
    # Deaths of one kind close together are one death of many.
    out.sort(key=lambda d: d["at"])
    merged: list[dict] = []
    for d in out:
        last = merged[-1] if merged else None
        if last and last["how"] == d["how"] and (d["at"] - last["at"]).total_seconds() < 3600:
            last["count"] += d["count"]
        else:
            merged.append(dict(d))
    # Rare deaths first (storms, replacements, empty houses), then the quiet
    # ones spread evenly over the day.
    rare = [d for d in merged if d["how"] != "отпущен тихо, когда схлынула толпа"]
    quiet = [d for d in merged if d not in rare]
    picked = rare[:limit]
    room = limit - len(picked)
    if room > 0 and quiet:
        step = max(1, len(quiet) / room)
        picked += [quiet[int(i * step)] for i in range(min(room, len(quiet)))]
    for d in picked:
        d["local"] = d["at"].astimezone(zone).strftime("%H:%M")
    return sorted(picked[:limit], key=lambda d: d["at"])


def life_words(hours: float) -> str:
    if hours < 1:
        return "жил меньше часа"
    if hours < 24:
        return f"жил несколько часов"
    if hours < 24 * 14:
        return f"жил несколько дней"
    if hours < 24 * 90:
        return "жил несколько недель"
    return "жил долго, месяцы"


def collection(material: dict, ops_path: Path, out: Path, tz: str) -> dict:
    a, b = datetime.fromisoformat(material["from"]), datetime.fromisoformat(material["to"])
    facts = json.loads((ops_path.parent / "facts.json").read_text())
    ds = deaths(ops_path, a, b, tz, incidents=facts["incidents"])
    month = b.astimezone(ZoneInfo(tz)).month if b.astimezone(ZoneInfo(tz)).day > 1 else a.astimezone(ZoneInfo(tz)).month
    season = SEASON[month]
    nb: list = []
    w = Writer(nb, effort="medium", data_class="private")
    system = ("Ты — японский поэт, пишущий по-русски. Ты пишешь дзисэй — предсмертные стихи. Три строки, 5–7–5 слогов. "
              "Обязательно сезонное слово. Образ ухода через природу и вещи, без называния смерти прямо. "
              "Никогда не упоминай технику, машины, компьютеры, программы. Не повторяй образы предыдущих стихов.")
    poems, used = [], []
    for d in ds:
        for attempt in range(4):
            prompt = (f"Время года: {season}. Время дня: {d['local']}. Тот, кто уходит, {life_words(d['life_hours'])}; "
                      f"как ушёл: {d['how']}." + (f" Ушли сразу многие ({d['count']})." if d["count"] > 3 else "") +
                      ("\nУже написаны (не повторяй их образов):\n" + "\n".join(" / ".join(p) for p in used) if used else ""))
            p = w.ask(system, prompt, Poem, f"jisei:{d['local']}:{attempt}", max_tokens=4000)
            counts = [syllables(x) for x in p.lines]
            leak = [x for x in FORBIDDEN_WORDS if x in " ".join(p.lines).lower()]
            nb.append({"check": {"syllables": counts, "leaks": leak}})
            if counts == [5, 7, 5] and not leak:
                break
        poems.append({"at": d["local"], "how": d["how"], "lines": p.lines, "syllables": counts, "ok": counts == [5, 7, 5] and not leak})
        used.append(p.lines)
    stem = f"{material['cluster']}_{material['window'].replace(':', '_')}_jisei"
    out.mkdir(parents=True, exist_ok=True)
    text = "\n\n".join("\n".join(p["lines"]) for p in poems)
    (out / f"{stem}.md").write_text(f"# Дзисэй. {season.capitalize()}\n\n{text}\n")
    (out / f"{stem}.json").write_text(json.dumps({"season": season, "poems": poems, "notebook": nb}, ensure_ascii=False, indent=1, default=str))
    return {"poems": len(poems), "ok": sum(p["ok"] for p in poems)}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("materials", nargs="+", type=Path)
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--out", type=Path, default=Path("out/works/literature"))
    ap.add_argument("--dry", action="store_true", help="list the deaths only")
    a = ap.parse_args()
    for p in a.materials:
        m = json.loads(p.read_text())
        facts = json.loads((a.scenarios / m["cluster"] / "facts.json").read_text())
        if a.dry:
            ds = deaths(a.scenarios / m["cluster"] / "ops.jsonl", datetime.fromisoformat(m["from"]),
                        datetime.fromisoformat(m["to"]), facts["timezone"], incidents=facts["incidents"])
            for d in ds:
                print(m["cluster"], d["local"], d["how"], round(d["life_hours"], 1), d["count"])
            continue
        print(collection(m, a.scenarios / m["cluster"] / "ops.jsonl", a.out, facts["timezone"]))


if __name__ == "__main__":
    main()
