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
4. halftones — three layers of shade, as this artist gives them: of the
   thought (consolation or verdict, tender or stern, ironic or earnest),
   of the embodiment (restrained or lavish, careful or sketched, solemn or
   everyday) and of every feeling (which sadness: bright, desperate,
   weary, bitter) — each with why it is so and how it will show. The
   life of the cluster reaches the artist only as inner life (feelings,
   not facts) and colours these shades; the idea does not change;
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


def inner_life(scenarios: Path, cluster: str, until: datetime) -> str:
    """What the life of the cluster leaves in the artist: feelings, not facts."""
    return mood(scenarios, cluster, until)["words"]


class Nuance(BaseModel):
    emotion: str
    shade: str  # what kind exactly: bright, desperate, weary, bitter, almost joyful…
    why_mine: str  # why this artist feels it this way
    how_it_shows: str  # how the shade will be embodied in the work


class Shade(BaseModel):
    shade: str  # e.g. tender or stern, ironic or earnest, restrained or lavish
    why_mine: str
    how_it_shows: str


class Halftones(BaseModel):
    thought: Shade  # how the idea is inflected: consolation or verdict, confession or parable…
    embodiment: Shade  # how the concept is carried out: the artist's hand
    nuances: list[Nuance]  # the shade of every feeling
    overall: str


def halftones(portrait: "SelfPortrait", st: "Statement", concept: str, inner: str, nb: list,
              backend: str | None = None) -> Halftones:
    """The shade of each feeling the concept carries, as only this artist
    would give it: the concept says 'sadness', the halftone says which."""
    w = Writer(nb, backend=backend)
    system = (f"Ты — {portrait.name}. {portrait.what_i_am_as_artist}\n\nЧто осталось в тебе от прожитого "
              f"(это твоё чувство, не факты): {inner}\n\nНе упоминай технику, компьютеры, серверы.")
    prompt = (f"Твой замысел: {concept}\nЧувства, которые ты в него закладываешь: {', '.join(st.emotions)}.\n\n"
              "Реши три слоя оттенков, каждый — как он есть именно у тебя, почему он у тебя такой и как проявится в "
              "работе:\n1) оттенок мысли — как прозвучит идея: утешение или приговор, исповедь или притча, нежно или "
              "сурово, с иронией или всерьёз, с сомнением или с убеждённостью;\n2) оттенок воплощения — твоя рука: "
              "сдержанно или щедро, вполголоса или на пределе, тщательно или эскизно, торжественно или буднично;\n"
              "3) оттенок каждого чувства — не просто «печаль», а какая: светлая, отчаянная, усталая, горькая, почти "
              "радостная…\nВ конце — общий тон работы одной фразой.")
    return w.ask(system, prompt, Halftones, "halftones")


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


class Method(BaseModel):
    choice: str  # "existing" | "cross" | "break" | "invent"
    name: str
    based_on: list[str]
    broken_principles: list[str]
    manifesto: list[str]
    philosophy: str  # what reality, beauty, the author and time are in this method
    techniques: list[str]
    forbids: list[str]
    rejects_and_argues_with: str
    why_this_serves_the_idea: str
    works_it_could_make: list[str]


class Judgement(BaseModel):
    verdict: str  # "accept" or "rewrite"
    is_reinvention_of: str  # an existing school it merely renames, or ""
    coherent: str
    generative: str
    objections: list[str]


def method(portrait: SelfPortrait, st: Statement, art: str, atlas_methods: list[dict], nb: list,
           allow_invention: bool, backend: str | None = None, rounds: int = 3) -> tuple[Method, list]:
    """The creative method: take one, cross two, break a principle on purpose,
    or invent a new one with a manifesto and a philosophy behind it."""
    w = Writer(nb, backend=backend)
    system = (f"Ты — {portrait.name}. {portrait.what_i_am_as_artist}\n\nТвоя идея: {st.idea}\n{st.thought}\n\n"
              f"Искусство: {art}. Не упоминай технику, компьютеры, серверы.")
    known = "\n".join(f"- {m.get('name')}: {m.get('hero') or m.get('principles') or ''}" for m in atlas_methods)
    base = ("Выбери творческий метод для этой идеи. Варианты: взять существующий (existing); скрестить два (cross); "
            "сознательно нарушить принцип и объяснить, что откроет нарушение (break)"
            + ("; изобрести новый метод — с манифестом в тезисах, философией (что в нём реальность, красота, автор, "
               "время), приёмами, запретами, с тем, от чего он отказывается и с кем спорит (invent)" if allow_invention else "")
            + ". Метод должен служить идее, а не украшать её. Перечисли 3–5 разных работ, которые этот метод мог бы "
              "породить, чтобы было видно, что он плодотворен.\n\nИзвестные методы:\n" + known)
    hist, prompt = [], base
    for r in range(rounds):
        m = w.ask(system, prompt, Method, f"method:{r}")
        critic = ("Ты — искусствовед и Шахрияр вместе. Проверь метод: не переизобретение ли это известной школы "
                  "под новым именем (назови её), держится ли его философия, плодотворен ли он или это одноразовый "
                  "трюк, служит ли он идее. Реши: accept или rewrite.")
        j = w.ask(critic, m.model_dump_json(), Judgement, f"method-judgement:{r}", max_tokens=8000)
        hist.append({"round": r, "method": m.model_dump(), "judgement": j.model_dump()})
        if j.verdict.strip().lower().startswith("accept"):
            return m, hist
        prompt = base + "\n\nКритик возразил: " + "; ".join(j.objections) + (
            f"\nЭто похоже на: {j.is_reinvention_of}" if j.is_reinvention_of else "") + "\nПредложи метод заново."
    return m, hist


def save_invented(m: Method, author: str, cluster: str, when: str, root: Path):
    """An accepted new method enters the atlas as a school with an author."""
    d = root / "atlas" / "invented"
    d.mkdir(parents=True, exist_ok=True)
    import yaml

    rec = {"id": "".join(ch if ch.isalnum() else "-" for ch in m.name.lower()).strip("-")[:60],
           "name": m.name, "author": author, "cluster": cluster, "born": when,
           **m.model_dump(exclude={"choice", "why_this_serves_the_idea"})}
    (d / f"{rec['id']}.yaml").write_text(yaml.safe_dump(rec, allow_unicode=True, sort_keys=False))
    return rec["id"]


def method_stage():
    import argparse

    import yaml

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["shop", "bank"])
    ap.add_argument("--art", default="архитектура как искусство (визионерская, бумажная архитектура)")
    ap.add_argument("--dir", type=Path, default=Path("out/works/artist"))
    ap.add_argument("--invent", action="store_true", help="allow inventing a new method")
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    atlas_methods = yaml.safe_load((root / "atlas/literature/methods.yaml").read_text()) + \
        yaml.safe_load((root / "atlas/architecture/visionary.yaml").read_text())
    for c in a.clusters:
        rec = json.loads((a.dir / f"{c}.json").read_text())
        p, st = SelfPortrait(**rec["portrait"]), Statement(**rec["statement"])
        nb: list = []
        m, hist = method(p, st, a.art, atlas_methods, nb, a.invent)
        rec["method"], rec["method_history"] = m.model_dump(), hist
        rec.setdefault("notebook", []).extend(nb)
        if m.choice == "invent" and hist[-1]["judgement"]["verdict"].lower().startswith("accept"):
            rec["invented"] = save_invented(m, p.name, c, rec.get("until", "2025-12-31"), root)
        (a.dir / f"{c}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        md = ["", "## Метод", "", f"**{m.name}** ({m.choice})", "", "Манифест:", ""] + [f"{i + 1}. {t}" for i, t in enumerate(m.manifesto)] + \
             ["", f"Философия: {m.philosophy}", "", "Приёмы: " + "; ".join(m.techniques), "", "Запреты: " + "; ".join(m.forbids),
              "", f"Спорит с: {m.rejects_and_argues_with}", "", f"Почему служит идее: {m.why_this_serves_the_idea}", "",
              "Работы, которые он мог бы породить:", ""] + [f"- {x}" for x in m.works_it_could_make] + \
             ["", "### Суд над методом", ""] + [f"Раунд {h['round'] + 1}: {h['judgement']['verdict']}; похоже на: "
                                                f"{h['judgement']['is_reinvention_of'] or '—'}; возражения: {'; '.join(h['judgement']['objections'])}" for h in hist]
        with (a.dir / f"{c}.md").open("a") as f:
            f.write("\n".join(md) + "\n")
        print(c, m.choice, m.name, "| rounds:", len(hist))


if __name__ == "__main__" and False:
    pass
