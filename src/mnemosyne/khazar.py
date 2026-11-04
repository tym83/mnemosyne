"""A Khazar dictionary of an incident (after Milorad Pavić).

The incident is told by three witnesses who never agree: the keeper of
the record (what the store and the controllers wrote down), the land (what
the nodes felt: pods falling, waiting, heat), and the people (what the
crowd and the person on watch did). From each witness the code builds an
account — times, order, weights — and the model writes three books of a
lexicon about an invented vanished people, Red, Green and Yellow, whose
entries contradict each other exactly where the witnesses do. No server,
pod or log is ever named; the key to the correspondences stays in the
notebook.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from pydantic import BaseModel

from .literature import FORBIDDEN_WORDS, Writer


class Entry(BaseModel):
    headword: str
    text: str
    see_also: list[str]


class Book(BaseModel):
    colour: str
    narrator: str
    entries: list[Entry]


class Lexicon(BaseModel):
    title: str
    people: str
    preface: str
    books: list[Book]
    diary: str


def deed(o: dict) -> str:
    """What a change was, told without technical words."""
    r, kind, op = o["reason"] or "", o["object"]["kind"], o["op"]
    if kind == "Node":
        return "поставил новый дом" if op == "create" else "разобрал пустой дом"
    if r == "autoscale":
        return "позвал ещё рук или отпустил лишние"
    if "rollback" in r:
        return "вернул прежний порядок"
    if r.startswith("scale-up"):
        return "позвал подмогу"
    if r.startswith("restart"):
        return "разбудил уснувших заново"
    if "degraded" in r:
        return "велел беречь силы и работать вполсилы"
    if "back to normal" in r:
        return "снял запрет, велел работать в полную силу"
    if r.startswith("release"):
        return "ввёл новый порядок"
    if r == "tuning":
        return "подправил уклад"
    if r == "scale down":
        return "отпустил лишних"
    return "сделал запись"


def witnesses(material: dict, scenarios: Path) -> dict:
    c = material["cluster"]
    facts = json.loads((scenarios / c / "facts.json").read_text())
    z = ZoneInfo(facts["timezone"])
    a, b = datetime.fromisoformat(material["from"]), datetime.fromisoformat(material["to"])
    inc = max((x for x in facts["incidents"] if a <= datetime.fromisoformat(x["start"]) < b), key=lambda x: x["severity"])
    s0, s1 = datetime.fromisoformat(inc["start"]), datetime.fromisoformat(inc["end"])
    hhmm = lambda t: t.astimezone(z).strftime("%H:%M")
    # The record: what was written down, in order, by whom (role, not name).
    record = []
    for line in (scenarios / c / "ops.jsonl").open():
        o = json.loads(line)
        t = datetime.fromisoformat(o["at"])
        if t > s1 + timedelta(hours=1):
            break
        if t >= s0 - timedelta(minutes=30):
            who = {"human": "дежурный", "gitops": "летописец порядка", "controller": "множащий помощник"}[o["actor_kind"]]
            what = deed(o)
            if record and record[-1]["who"] == who and record[-1]["what"] == what:
                record[-1]["times"] = record[-1].get("times", 1) + 1
                continue
            record.append({"time": hhmm(t), "who": who, "what": what})
    # The land: what the ground felt, from the signals.
    sig = dict(np.load(scenarios / c / "signals.npz"))
    i0 = int((s0 - datetime.fromisoformat(facts["start"])).total_seconds() // 300)
    i1 = int((s1 - datetime.fromisoformat(facts["start"])).total_seconds() // 300)
    seg = slice(max(0, i0 - 6), i1 + 12)
    unready, lat = sig["unready"][seg], sig["latency_ms"][seg]
    land = {"first_tremor": hhmm(s0), "worst": hhmm(s0 + timedelta(minutes=5 * int(np.argmax(unready)))),
            "fallen_share_at_worst": round(float(unready.max()), 2),
            "waiting_grew_times": round(float(lat.max() / max(np.median(sig["latency_ms"]), 1)), 1),
            "quiet_again": hhmm(s1)}
    # The people: the crowd and the one on watch.
    load = sig["load"][seg]
    people = {"crowd_vs_usual": round(float(load.max()), 1),
              "watch_acted_at": [x["at"] for x in inc["actions"]],
              "deeds": [{"scale-up": "позвал подмогу", "restart": "разбудил уснувших", "rollback": "вернул прежний порядок",
                         "degraded-mode": "велел работать вполсилы", "normal-mode": "снял запрет"}.get(x["what"], x["what"])
                        for x in inc["actions"]],
              "struck_first": "тот, кто принимает плату" if inc["service"].startswith("pay") else "один из работников",
              "also_hurt": len(inc["affected"]) - 1}
    for d in people["watch_acted_at"]:
        pass
    people["watch_acted_at"] = [hhmm(datetime.fromisoformat(x)) for x in people["watch_acted_at"]]
    return {"record": record[:40], "land": land, "people": people, "severity": inc["severity"],
            "key": {"incident": inc["start"], "service": inc["service"]}}


def write(material: dict, scenarios: Path, out: Path) -> dict:
    wit = witnesses(material, scenarios)
    nb: list = [{"step": "witnesses", "accounts": wit}]
    w = Writer(nb, data_class="private")
    system = ("Ты пишешь в манере «Хазарского словаря» Милорада Павича: роман-лексикон об исчезнувшем выдуманном "
              "народе, три книги — Красная, Зелёная, Жёлтая — от трёх свидетелей одной и той же ночи. Каждая книга "
              "искренне уверена в своей правде, и книги противоречат друг другу. Статьи — по алфавиту, со ссылками "
              "друг на друга (see_also — заголовки статей из любой книги). Язык живой, сказочный, точный в деталях. "
              "Никогда не упоминай технику, машины, компьютеры, программы, сети.")
    prompt = ("Три свидетеля одной ночи. Перескажи их показания через судьбу выдуманного народа, сохранив время, "
              "порядок и противоречия между ними (где один видит одно, другой — другое).\n\n"
              f"КРАСНАЯ КНИГА — хранитель записей. Его записи по времени:\n{json.dumps(wit['record'], ensure_ascii=False)}\n\n"
              f"ЗЕЛЁНАЯ КНИГА — земля. Что она чувствовала:\n{json.dumps(wit['land'], ensure_ascii=False)}\n\n"
              f"ЖЁЛТАЯ КНИГА — люди. Что делали толпа и дежурный:\n{json.dumps(wit['people'], ensure_ascii=False)}\n\n"
              "В каждой книге 6–9 статей по 150–350 слов. Предисловие — от составителя словаря. В diary — заметка "
              "от первого лица: что ты хотел сделать с этой ночью.")
    lex = w.ask(system, prompt, Lexicon, "lexicon", max_tokens=64000)
    text = [f"# {lex.title}", "", f"*{lex.people}*", "", lex.preface, ""]
    for bk in lex.books:
        text += [f"## {bk.colour} книга", "", f"*{bk.narrator}*", ""]
        for e in sorted(bk.entries, key=lambda e: e.headword):
            text += [f"### {e.headword}", "", e.text, ""]
            if e.see_also:
                text += ["См. также: " + ", ".join(e.see_also), ""]
    body = "\n".join(text)
    leaks = [x for x in FORBIDDEN_WORDS if x in body.lower()]
    stem = f"{material['cluster']}_{material['window'].replace(':', '_')}_khazar"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.md").write_text(body)
    (out / f"{stem}.json").write_text(json.dumps({"material": material["window"], "title": lex.title,
                                                  "technical_leaks": leaks, "key": wit["key"], "notebook": nb},
                                                 ensure_ascii=False, indent=1))
    return {"title": lex.title, "entries": sum(len(b.entries) for b in lex.books), "leaks": leaks}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("material", type=Path)
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--out", type=Path, default=Path("out/works/literature"))
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    m = json.loads(a.material.read_text())
    if a.dry:
        print(json.dumps(witnesses(m, a.scenarios), ensure_ascii=False, indent=1)[:2500])
        return
    print(write(m, a.scenarios, a.out))


if __name__ == "__main__":
    main()
