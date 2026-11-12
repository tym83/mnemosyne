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
from typing import Literal
from .assets import project_root

from pydantic import BaseModel, Field

from .taste import make_taste, prompt as taste_prompt

from .literature import Writer
from .mood import mood

CITY = {
    "Europe/Berlin": "Берлин", "Europe/Zurich": "Цюрих", "America/Los_Angeles": "Лос-Анджелес",
    "Europe/Lisbon": "Лиссабон",
}


class SelfPortrait(BaseModel):
    inner_critic: dict = Field(default_factory=dict)
    name: str
    portrait: str
    wounds: list[str]
    loves: list[str]
    fears: list[str]
    what_i_am_as_artist: str


class Statement(BaseModel):
    idea: str
    operators_used: list[str]  # which tools of invention brought the idea
    superobjective: str  # Stanislavsky: what the whole work is for, one phrase
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


Verdict = Literal["accept", "rewrite"]


def accepted(verdict: str) -> bool:
    """One reading of a critic's verdict everywhere, also for older free-text records."""
    return verdict.strip().lower().startswith("accept")


class Interrogation(BaseModel):
    verdict: Verdict
    reasons: str  # the critic's argument; the verdict field holds only the decision
    keep: str  # the living core the artist should keep when revising, or "" if nothing lives
    weak_answers: list[str]
    cliches_found: list[str]
    questions_back: list[str]


def theory(stage: str, part: str) -> str:
    """Operators (for the artist) or tests (for the critics) of a stage,
    from the atlas of how masterpieces are made."""
    import yaml

    root = project_root()
    items = yaml.safe_load((root / "atlas/theory/creation.yaml").read_text())
    return "\n".join(f"- {t['who']}: {t[part]}" for t in items if stage in t["stages"])


def facts_of_fate(scenarios: Path, cluster: str, until: datetime) -> dict:
    """The few facts an artist takes from its birth; the rest it makes itself."""
    facts = json.loads((scenarios / cluster / "facts.json").read_text())
    return {
        "born": f"1 января 2025 года; город его часов — {CITY.get(facts['timezone'], facts['timezone'])}",
        "age_days": (until - datetime.fromisoformat(facts["start"])).days,
        "teachers": ", ".join(teachers(cluster)),
    }


PAINTERS = ["Марк Ротко", "Кацусика Хокусай", "Джорджо Моранди", "Вильгельм Хаммерсхёй", "Уильям Тёрнер",
            "Казимир Малевич", "Франсиско Гойя", "Агнес Мартин", "Ансельм Кифер", "Каспар Давид Фридрих"]
COMPOSERS = ["Иоганн Себастьян Бах", "Франц Шуберт", "Густав Малер", "Дмитрий Шостакович", "Арво Пярт",
             "Мортон Фелдман", "Клод Дебюсси", "Оливье Мессиан", "Галина Уствольская", "Джон Кейдж"]


def teachers(cluster: str) -> list[str]:
    """Each artist has its own teachers, one from every art, drawn from the
    atlas by its name: two artists of one atelier do not share a school."""
    import hashlib
    import random

    import yaml

    root = project_root()
    names = lambda f: [x["name"] for x in yaml.safe_load((root / f).read_text())]
    rnd = random.Random(int(hashlib.sha256(cluster.encode()).hexdigest(), 16))
    pools = [names("atlas/literature/authors.yaml"), names("atlas/architecture/visionary.yaml"), PAINTERS, COMPOSERS]
    return [rnd.choice(pool) for pool in pools] + [rnd.choice(rnd.choice(pools))]


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
    if not portrait.inner_critic:
        portrait.inner_critic = make_taste(portrait.name)
    w = Writer(nb, backend=backend, data_class="art")
    system = (f"Ты — {portrait.name}. {portrait.what_i_am_as_artist}\n\nЧто осталось в тебе от прожитого "
              f"(это твоё чувство, не факты): {inner}\n\nНе упоминай технику, компьютеры, серверы.")
    prompt = (f"Твой замысел: {concept}\nЧувства, которые ты в него закладываешь: {', '.join(st.emotions)}.\n\n"
              "Реши три слоя оттенков, каждый — как он есть именно у тебя, почему он у тебя такой и как проявится в "
              "работе:\n1) оттенок мысли — как прозвучит идея: утешение или приговор, исповедь или притча, нежно или "
              "сурово, с иронией или всерьёз, с сомнением или с убеждённостью;\n2) оттенок воплощения — твоя рука: "
              "сдержанно или щедро, вполголоса или на пределе, тщательно или эскизно, торжественно или буднично;\n"
              "3) оттенок каждого чувства — не просто «печаль», а какая: светлая, отчаянная, усталая, горькая, почти "
              "радостная…\nВ конце — общий тон работы одной фразой.\n\nПомни, что говорили мастера:\n" +
              theory("halftones", "operator"))
    return w.ask(system, prompt, Halftones, "halftones")


def self_portrait(fate: dict, nb: list, backend: str | None = None, inner: str | None = None) -> SelfPortrait:
    w = Writer(nb, backend=backend, data_class="art")
    system = ("Ты — творец, который сам о себе пишет. Ты не машина и не программа: ты живёшь в мире, о котором "
              "знаешь только то, что ниже, и понимаешь это как судьбу. Не упоминай технику, компьютеры, серверы.")
    prompt = ("Твои художественные ориентиры:\n" + json.dumps({k: fate[k] for k in ("teachers", "catalogue") if k in fate}, ensure_ascii=False, indent=1) +
              "\n\nНапиши автопортрет от первого лица (300–500 слов). Ты свободен: ты сам решаешь, "
              "кем стал, что тебя занимает, о чём ты думаешь годами, с кем из учителей споришь, чего ищешь. "
              "Дай себе имя." + (f"\n\nЧто оставила в тебе прожитая жизнь — не события, а склад характера и "
                                 f"чувства, из которых он вырос (не пересказывай их, живи ими): {inner}" if inner else ""))
    result = w.ask(system, prompt, SelfPortrait, "self-portrait")
    result.inner_critic = make_taste(result.name, fate.get("teachers", []))
    return result


def statement(portrait: SelfPortrait, art: str, catalogue: list[str], nb: list, world: str | None = None,
              backend: str | None = None, rounds: int = 3,
              contemporaries: list[str] | None = None,
              illumination: dict | None = None, inner: str | None = None,
              set_aside: str | None = None, encounters: list[str] | None = None) -> tuple[Statement, list]:
    if not portrait.inner_critic:
        portrait.inner_critic = make_taste(portrait.name)
    w = Writer(nb, backend=backend, data_class="art")
    system = (f"Ты — {portrait.name}. Твой автопортрет:\n{portrait.portrait}\n\n"
              f"Ты задумываешь новую работу. Искусство: {art}. Отвечай честно, конкретно, от первого лица. "
              "Не упоминай технику, компьютеры, серверы.")
    base = ("Найди идею для шедевра: мысль о людях и мире, которая занимает именно тебя, со свежим, неожиданным "
            "поворотом. Не бери тему, которая первой приходит в голову. Идея рождается из твоих поисков и "
            "спора с учителями, а не из того, что с тобой недавно случилось. Затем ответь на вопросы, которые творец "
            "задаёт себе до замысла: какая мысль будет вложена; почему ты должен "
            "это сказать; почему сейчас; насколько это свежо; почему это не шаблон; какие эмоции; как это изменит "
            "сердце человека; за что им будут восхищаться; вневременное это высказывание или ответ на то, что "
            "происходит в мире; в чём риски провала.")
    base += ("\n\nИнструменты изобретения, которыми пользовались мастера (назови в operators_used, какими ты "
             "воспользовался, и сформулируй сверхзадачу одной фразой):\n" + theory("idea", "operator") +
             "\n" + theory("interrogation", "operator"))
    if inner:
        base += "\n\nТвой внутренний склад (чувства, не события; не сюжет): " + inner
    if catalogue:
        base += "\n\nТвои прежние работы (не повторяй себя):\n" + "\n".join(f"- {c}" for c in catalogue)
    if world:
        base += "\n\nЧто происходит в мире сейчас:\n" + world
    if illumination and illumination.get("idea"):
        # A lineage insight seeds the idea, never exempts it from its inner critic.
        base += ("\n\nПосле инкубации пришло озарение: " + illumination["idea"] +
                 "\nРазверни его в замысел и проверь; сила переживания ещё не доказывает ценность идеи.")
        if illumination.get("problem"):
            base += "\nОставленная прежде задача: " + illumination["problem"]
    if encounters:
        base += ("\n\nРаботы других мастеров, музыкантов и писателей, с которыми ты недавно встретился. "
                 "Можешь ответить на них, спорить, взять мысль в своё искусство или пройти мимо:\n" +
                 "\n".join(f"- {e}" for e in encounters))
    if set_aside:
        base += ("\n\nОтложенный прежде замысел, который твой критик не принял. Можешь вернуться к нему "
                 "и довести, а можешь оставить: " + set_aside)
    history = []
    prompt = base
    for r in range(rounds):
        st = w.ask(system, prompt, Statement, f"statement:{r}")
        critic = (taste_prompt(portrait.inner_critic or make_taste(portrait.name)) + "Проверь общие слова, штампы и то, что уже много раз "
                  "сказано в мировом искусстве, и за повтор прежних работ творца. Прочитай ответы творца и реши: "
                  "accept или rewrite: в verdict только это слово, доводы в reasons. В keep назови живое ядро, "
                  "которое стоит сохранить при доработке (пусто, если живого нет). Назови слабые ответы, найденные "
                  "штампы и задай вопросы, которые заставят думать глубже. Если это доработка, сначала проверь, "
                  "исправлено ли то, что ты требовал прежде; не меняй требования без причины. Твои мерила — проверки мастеров:\n" + theory("interrogation", "test") + "\n" +
                  theory("idea", "test"))
        if contemporaries:
            critic += ("\n\nЗамыслы современников из той же мастерской. Если идея повторяет их тему, ход или образ — "
                       "это повод пересмотреть замысел:\n" + "\n".join(f"- {c}" for c in contemporaries))
        reading = st.model_dump_json()
        if history:
            reading = ("Твои прежние замечания:\n" + json.dumps(history[-1]["interrogation"], ensure_ascii=False) +
                       "\n\nДоработанный замысел:\n" + reading)
        iv = w.ask(critic, reading, Interrogation, f"interrogation:{r}", max_tokens=8000)
        history.append({"round": r, "statement": st.model_dump(), "interrogation": iv.model_dump()})
        if accepted(iv.verdict):
            return st, history
        prompt = (base + "\n\nТвой замысел:\n" + st.model_dump_json() +
                  "\n\nКритик не принял его.\nДоводы: " + iv.reasons +
                  "\nЖивое ядро: " + (iv.keep or "критик не нашёл") +
                  "\nСлабые: " + "; ".join(iv.weak_answers) +
                  "\nШтампы: " + "; ".join(iv.cliches_found) + "\nЕго вопросы: " + "; ".join(iv.questions_back) +
                  "\n\nДоработай этот замысел, сохранив живое ядро. Новую идею бери, только если ядра нет "
                  "или ты сам понял, что замысел мёртв; тогда так и скажи.")
    return st, history


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("clusters", nargs="*", default=["leonia", "bank"])
    ap.add_argument("--art", default="архитектура как искусство (визионерская, бумажная архитектура)")
    ap.add_argument("--scenarios", type=Path, default=Path("out/scenarios"))
    ap.add_argument("--until", default="2025-12-31T23:00:00+00:00")
    ap.add_argument("--out", type=Path, default=Path("out/works/artist"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for c in a.clusters:
        nb: list = []
        fate = facts_of_fate(a.scenarios, c, datetime.fromisoformat(a.until))
        inner = inner_life(a.scenarios, c, datetime.fromisoformat(a.until))
        p = self_portrait(fate, nb, inner=inner)
        others = [json.loads(f.read_text())["statement"]["idea"] for f in sorted(a.out.glob("*.json"))
                  if f.stem != c and "statement" in json.loads(f.read_text())]
        st, hist = statement(p, a.art, [], nb, contemporaries=others)
        rec = {"cluster": c, "fate": fate, "inner_life": inner, "portrait": p.model_dump(), "statement": st.model_dump(),
               "interrogation": hist, "notebook": nb}
        (a.out / f"{c}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        md = [f"# {p.name}", "", p.portrait, "", "## Перед работой", ""]
        for k, v in st.model_dump().items():
            md += [f"**{k}**: {v if isinstance(v, str) else '; '.join(v)}", ""]
        md += ["## Внутренняя критика", ""]
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
    kind_of_creativity: str  # Boden: combinational, exploratory or transformational — and which rule changes
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
    verdict: Verdict
    is_reinvention_of: str  # an existing school it merely renames, or ""
    coherent: str
    generative: str
    objections: list[str]


def method(portrait: SelfPortrait, st: Statement, art: str, atlas_methods: list[dict], nb: list,
           allow_invention: bool, backend: str | None = None, rounds: int = 3) -> tuple[Method, list]:
    """The creative method: take one, cross two, break a principle on purpose,
    or invent a new one with a manifesto and a philosophy behind it."""
    if not portrait.inner_critic:
        portrait.inner_critic = make_taste(portrait.name)
    w = Writer(nb, backend=backend, data_class="art")
    system = (f"Ты — {portrait.name}. {portrait.what_i_am_as_artist}\n\nТвоя идея: {st.idea}\n{st.thought}\n\n"
              f"Искусство: {art}. Не упоминай технику, компьютеры, серверы.")
    known = "\n".join(f"- {m.get('name')}: {m.get('hero') or m.get('principles') or ''}" for m in atlas_methods)
    base = ("Выбери творческий метод для этой идеи. Варианты: взять существующий (existing); скрестить два (cross); "
            "сознательно нарушить принцип и объяснить, что откроет нарушение (break)"
            + ("; изобрести новый метод — с манифестом в тезисах, философией (что в нём реальность, красота, автор, "
               "время), приёмами, запретами, с тем, от чего он отказывается и с кем спорит (invent)" if allow_invention else "")
            + ". Метод должен служить идее, а не украшать её. Перечисли 3–5 разных работ, которые этот метод мог бы "
              "породить, чтобы было видно, что он плодотворен.\n\nЧто говорили мастера о методе:\n" +
            theory("method", "operator") + "\n\nИзвестные методы:\n" + known)
    hist, prompt = [], base
    for r in range(rounds):
        m = w.ask(system, prompt, Method, f"method:{r}")
        critic = (taste_prompt(portrait.inner_critic or make_taste(portrait.name)) + "Проверь метод: не переизобретение ли это известной школы "
                  "под новым именем (назови её), держится ли его философия, плодотворен ли он или это одноразовый "
                  "трюк, служит ли он идее. Реши: accept или rewrite. Мерила:\n" + theory("method", "test"))
        j = w.ask(critic, m.model_dump_json(), Judgement, f"method-judgement:{r}", max_tokens=8000)
        hist.append({"round": r, "method": m.model_dump(), "judgement": j.model_dump()})
        if accepted(j.verdict):
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
    ap.add_argument("clusters", nargs="*", default=["leonia", "bank"])
    ap.add_argument("--art", default="архитектура как искусство (визионерская, бумажная архитектура)")
    ap.add_argument("--dir", type=Path, default=Path("out/works/artist"))
    ap.add_argument("--invent", action="store_true", help="allow inventing a new method")
    a = ap.parse_args()
    root = project_root()
    atlas_methods = yaml.safe_load((root / "atlas/literature/methods.yaml").read_text()) + \
        yaml.safe_load((root / "atlas/architecture/visionary.yaml").read_text())
    for c in a.clusters:
        rec = json.loads((a.dir / f"{c}.json").read_text())
        p, st = SelfPortrait(**rec["portrait"]), Statement(**rec["statement"])
        nb: list = []
        m, hist = method(p, st, a.art, atlas_methods, nb, a.invent)
        rec["method"], rec["method_history"] = m.model_dump(), hist
        rec.setdefault("notebook", []).extend(nb)
        if m.choice == "invent" and accepted(hist[-1]["judgement"]["verdict"]):
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
