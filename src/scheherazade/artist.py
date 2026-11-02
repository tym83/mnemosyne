"""Who the artist is, and what it wants to say before it makes anything.

A masterpiece starts with an idea, not with data. The order is:

1. idea — a thought about people and the world (time, memory, love, home,
   loss, freedom, faith, solitude…) with a fresh turn; it comes from the
   artist's own inquiry, its quarrel with its teachers and, if wanted,
   from the world — never from the cluster;
2. interrogation — the questions any artist asks (why say it, why now,
   how fresh, is it a cliché, what will a heart feel); a critic sends weak
   answers back;
3. concept in a given art;
4. halftones — only now the life of the cluster tints the found concept:
   warmer or colder light, rougher or smoother surface, tempo, density,
   the weight of the ending. The idea does not change;
5. sketches and drafts.

The artist's identity takes only birth and age from facts; who it became
it composes itself from its works, teachers and crises, with the life of
the cluster again giving only halftones.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from .literature import Writer
from .mood import mood

CITY = {
    "Europe/Berlin": "Берлин", "Europe/Zurich": "Цюрих", "America/Los_Angeles": "Лос-Анджелес",
    "Europe/Lisbon": "Лиссабон",
}


class SelfPortrait(BaseModel):
    name: str
    portrait: str
    wounds: list[str]
    loves: list[str]
    fears: list[str]
    what_i_am_as_artist: str


class Statement(BaseModel):
    idea: str
    thought: str
    why_i_must_say_it: str
    why_now: str
    freshness: str
    not_a_cliche_because: str
    emotions: list[str]
    how_it_changes_a_heart: str
    why_admired: str
    timeless_or_of_the_world: str
    risks: list[str]


class Interrogation(BaseModel):
    verdict: str  # "accept" or "rewrite"
    weak_answers: list[str]
    cliches_found: list[str]
    questions_back: list[str]


def facts_of_fate(scenarios: Path, cluster: str, until: datetime) -> dict:
    """The few facts an artist takes from its birth; the rest it makes itself."""
    facts = json.loads((scenarios / cluster / "facts.json").read_text())
    return {
        "born": f"1 января 2025 года; город его часов — {CITY.get(facts['timezone'], facts['timezone'])}",
        "age_days": (until - datetime.fromisoformat(facts["start"])).days,
        "teachers": "Чехов, Гоголь, Лесков, Элюар; Ротко, Хокусай; Булле, Леонидов, Андо",
    }


def halftones(scenarios: Path, cluster: str, until: datetime) -> dict:
    """How the life of the cluster may tint a work already conceived:
    soft directions, never subjects."""
    q = mood(scenarios, cluster, until)["qualities"]
    pick = lambda x, a, b, c: a if x < 0.33 else b if x < 0.66 else c
    return {
        "light": pick(q["scars"], "ровный, рассеянный", "с тенями", "резкий, контрастный"),
        "temperature": pick(q["crowding"], "прохладная", "умеренная", "тёплая, почти жаркая"),
        "surface": pick(1 - q["steadiness"], "гладкая, спокойная", "живая", "шероховатая, взволнованная"),
        "tempo": pick(q["volatility"], "медленный", "переменчивый", "порывистый"),
        "density": pick(q["density"], "разреженная", "средняя", "плотная"),
        "enclosure": pick(q["closedness"], "открытость", "полуоткрытость", "замкнутость"),
        "ending": pick(q["loss"], "светлая", "с горечью", "с утратой"),
    }


def self_portrait(fate: dict, nb: list, backend: str | None = None) -> SelfPortrait:
    w = Writer(nb, backend=backend)
    system = ("Ты — художник, который сам о себе пишет. Ты не машина и не программа: ты живёшь в мире, о котором "
              "знаешь только то, что ниже, и понимаешь это как судьбу. Не упоминай технику, компьютеры, серверы.")
    prompt = ("Факты твоей судьбы:\n" + json.dumps(fate, ensure_ascii=False, indent=1) +
              "\n\nНапиши автопортрет от первого лица (300–500 слов). Кроме этих фактов ты свободен: ты сам решаешь, "
              "кем стал, что тебя занимает, о чём ты думаешь годами, с кем из учителей споришь, чего ищешь. "
              "Дай себе имя.")
    return w.ask(system, prompt, SelfPortrait, "self-portrait")


def statement(portrait: SelfPortrait, art: str, catalogue: list[str], nb: list, world: str | None = None,
              backend: str | None = None, rounds: int = 3) -> tuple[Statement, list]:
    w = Writer(nb, backend=backend)
    system = (f"Ты — {portrait.name}. Твой автопортрет:\n{portrait.portrait}\n\n"
              f"Ты задумываешь новую работу. Искусство: {art}. Отвечай честно, конкретно, от первого лица. "
              "Не упоминай технику, компьютеры, серверы.")
    base = ("Найди идею для шедевра: мысль о людях и мире (о времени, памяти, любви, доме, утрате, свободе, вере, "
            "одиночестве — или о чём-то ещё) со свежим, неожиданным поворотом. Идея рождается из твоих поисков и "
            "спора с учителями, а не из того, что с тобой недавно случилось. Затем ответь на вопросы, которые художник "
            "задаёт себе до замысла: какая мысль будет вложена; почему ты должен "
            "это сказать; почему сейчас; насколько это свежо; почему это не шаблон; какие эмоции; как это изменит "
            "сердце человека; за что им будут восхищаться; вневременное это высказывание или ответ на то, что "
            "происходит в мире; в чём риски провала.")
    if catalogue:
        base += "\n\nТвои прежние работы (не повторяй себя):\n" + "\n".join(f"- {c}" for c in catalogue)
    if world:
        base += "\n\nЧто происходит в мире сейчас:\n" + world
    history = []
    prompt = base
    for r in range(rounds):
        st = w.ask(system, prompt, Statement, f"statement:{r}")
        critic = ("Ты — Шахрияр, беспощадный критик. Ты казнишь за общие слова, за штампы, за то, что уже тысячу раз "
                  "сказано в мировом искусстве, и за повтор прежних работ художника. Прочитай ответы художника и реши: "
                  "accept или rewrite. Назови слабые ответы, найденные штампы и задай вопросы, которые заставят "
                  "думать глубже.")
        iv = w.ask(critic, st.model_dump_json(), Interrogation, f"interrogation:{r}", max_tokens=8000)
        history.append({"round": r, "statement": st.model_dump(), "interrogation": iv.model_dump()})
        if iv.verdict.strip().lower().startswith("accept"):
            return st, history
        prompt = (base + "\n\nКритик отверг прошлые ответы.\nСлабые: " + "; ".join(iv.weak_answers) +
                  "\nШтампы: " + "; ".join(iv.cliches_found) + "\nЕго вопросы: " + "; ".join(iv.questions_back) +
                  "\n\nОтветь заново, глубже и конкретнее.")
    return st, history


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    ap.add_argument("--art", default="архитектура как искусство (визионерская, бумажная архитектура)")
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--until", default="2025-12-31T23:00:00+00:00")
    ap.add_argument("--out", type=Path, default=Path("out/works/artist"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for c in a.clusters:
        nb: list = []
        fate = facts_of_fate(a.scenarios, c, datetime.fromisoformat(a.until))
        p = self_portrait(fate, nb)
        st, hist = statement(p, a.art, [], nb)
        rec = {"cluster": c, "fate": fate, "portrait": p.model_dump(), "statement": st.model_dump(),
               "interrogation": hist, "notebook": nb}
        (a.out / f"{c}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        md = [f"# {p.name}", "", p.portrait, "", "## Перед работой", ""]
        for k, v in st.model_dump().items():
            md += [f"**{k}**: {v if isinstance(v, str) else '; '.join(v)}", ""]
        md += ["## Допрос Шахрияра", ""]
        for h in hist:
            md += [f"Раунд {h['round'] + 1}: {h['interrogation']['verdict']}", "",
                   "Штампы: " + "; ".join(h["interrogation"]["cliches_found"]), "",
                   "Вопросы: " + "; ".join(h["interrogation"]["questions_back"]), ""]
        (a.out / f"{c}.md").write_text("\n".join(md))
        print(c, p.name, "| rounds:", len(hist), "| verdict:", hist[-1]["interrogation"]["verdict"])


if __name__ == "__main__":
    main()
