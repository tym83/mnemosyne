"""Stories from the material of a window, written by a language model inside
frames the code decides.

The model never chooses the world, the method or the teacher: a diversity
step picks them from the atlas. It is never told about the cluster either —
it receives a skeleton of story functions and writes a human story in an
invented world that carries the same form (a roman à clef: the key stays in
the notebook). Every step is a separate, structured request; every
candidate, verdict and the artist's own diary go to the notebook.

Model calls go through the Anthropic API (Claude Opus 5.5) with adaptive
thinking, structured JSON outputs, the server-side refusal fallback and a
cached prefix holding the atlas cards and the language exemplars.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel

ATLAS = Path(__file__).resolve().parents[2] / "atlas" / "literature"
MODEL = "claude-opus-5-5"

FUNCTIONS_RU = {
    "trouble": "беда", "struggle": "борьба героя", "helper": "помощник", "restoration": "восстановление",
    "return-of-the-old": "возвращение прежнего", "crowd": "наплыв, толпа, праздник", "fast": "пост, бдение",
    "arrival": "прибытие нового", "loss": "утрата", "new-period": "новая эпоха", "journey": "путешествие",
    "silence": "тишина",
}

FORBIDDEN_WORDS = ["сервер", "кластер", "под ", "контейнер", "kubernetes", "лог", "сервис", "деплой", "релиз",
                   "нода", "реплик", "база данных", "компьютер", "интернет", "сеть "]


class Character(BaseModel):
    name: str
    role_in_skeleton: str
    desire: str
    fear: str


class Synopsis(BaseModel):
    title: str
    characters: list[Character]
    skeleton_mapping: dict[str, str]
    concrete_details: list[str]
    central_image: str
    ending: str
    synopsis: str
    diary: str  # the artist's note, first person, on why this story


class Scene(BaseModel):
    function: str
    where: str
    who: list[str]
    what_changes: str
    detail: str


class Plan(BaseModel):
    scenes: list[Scene]
    diary: str


class SceneText(BaseModel):
    text: str


class Verdict(BaseModel):
    best: int
    reasons: str
    problems: list[str]


class Edit(BaseModel):
    text: str
    changes: list[str]
    diary: str


def atlas():
    load = lambda n: yaml.safe_load((ATLAS / f"{n}.yaml").read_text())
    return load("methods"), load("authors"), load("worlds")


def exemplars(author: str, limit: int = 3) -> list[str]:
    d = ATLAS / "exemplars" / author
    if not d.exists():
        return []
    return [p.read_text()[:2500] for p in sorted(d.glob("*.txt"))[:limit]]


def skeleton_ru(material: dict) -> list[dict]:
    out = []
    for act in material["skeleton"]:
        for f in act["functions"]:
            out.append({"function": FUNCTIONS_RU.get(f["function"], f["function"]),
                        "weight": round(min(1.0, float(act.get("weight") or 0.5)), 2)})
    return out


def points(material: dict, catalogue: list[dict], k: int, seed: int) -> list[dict]:
    """Diversity, by code: method × author × world, far from what the
    catalogue already holds and fitting the skeleton's tags."""
    methods, authors, worlds = atlas()
    rng = np.random.default_rng(seed)
    funcs = {f["function"] for a in material["skeleton"] for f in a["functions"]}
    want = {"trouble": ["storm", "trouble", "danger"], "crowd": ["crowd", "feast", "many"], "helper": ["helpers", "collective", "many"],
            "restoration": ["rescue", "light"], "loss": ["loss", "farewell"], "journey": ["journey"], "silence": ["silence", "solitude"],
            "fast": ["fast", "vigil"], "new-period": ["new-period", "time"]}
    tags = {t for f in funcs for t in want.get(f, [])}
    used = {(c.get("method"), c.get("author"), c.get("world")) for c in catalogue}
    cands = []
    for _ in range(600):
        m, a, w = (x[int(rng.integers(0, len(x)))] for x in (methods, authors, worlds))
        fit = len(tags & set(w["tags"])) / max(1, len(tags))
        novelty = 0 if (m["id"], a["id"], w["id"]) in used else 1
        novelty += sum(0.3 for c in catalogue if c.get("world") == w["id"]) * -1
        cands.append((0.6 * fit + 0.4 * novelty + rng.normal(0, 0.05), m, a, w))
    cands.sort(key=lambda x: -x[0])
    chosen = []
    for _, m, a, w in cands:
        if all(m["id"] != c["method"] and a["id"] != c["author"] and w["id"] != c["world"] for c in chosen):
            chosen.append({"method": m["id"], "author": a["id"], "world": w["id"], "_m": m, "_a": a, "_w": w})
        if len(chosen) == k:
            break
    return chosen


class Writer:
    """Asks a model for a structured answer through one of three doors:

    * codex  — Codex CLI on a ChatGPT subscription (`codex exec --output-schema`);
    * claude — Claude Code on a Claude subscription (`claude -p --json-schema`);
    * api    — the Anthropic API (Claude Opus 5.5, cached frame, refusal fallback).

    The CLIs run in an empty scratch directory with no tools, so they only
    write. Every answer is validated against its schema; a broken one is
    asked again.
    """

    def __init__(self, notebook: list, effort: str = "high", backend: str | None = None):
        import os

        self.notebook = notebook
        self.effort = effort
        self.backend = backend or os.environ.get("WRITER", "codex")
        if self.backend == "api":
            import anthropic

            self.client = anthropic.Anthropic()

    def ask(self, system: str, prompt: str, schema: type[BaseModel], step: str, max_tokens: int = 32000,
            images: list[Path] | None = None):
        """images: pictures the writer looks at (its own drafts); codex only."""
        import hashlib
        import os

        # Answers are kept on disk: a run that stops can be restarted without
        # asking again what was already answered.
        cache = Path(os.environ.get("WRITER_CACHE", "out/cache"))
        seen = [hashlib.sha256(Path(i).read_bytes()).hexdigest() for i in images or []]
        key = hashlib.sha256(json.dumps([self.backend, system, prompt, _schema(schema)] + seen,
                                        ensure_ascii=False).encode()).hexdigest()
        hit = cache / f"{key}.json"
        if hit.exists():
            out = schema.model_validate_json(hit.read_text())
            self.notebook.append({"step": step, "backend": self.backend, "cached": True, "result": out.model_dump()})
            return out
        last = None
        for attempt in range(3):
            try:
                if images and self.backend != "codex":
                    raise NotImplementedError(f"{self.backend}: looking at images")
                extra = {"images": images} if images else {}
                text, meta = getattr(self, f"_{self.backend}")(system, prompt, _schema(schema), max_tokens, **extra)
                out = schema.model_validate_json(text)
                cache.mkdir(parents=True, exist_ok=True)
                hit.write_text(out.model_dump_json())
                self.notebook.append({"step": step, "backend": self.backend, **meta, "result": out.model_dump()})
                return out
            except Exception as e:  # a broken answer is a sketch that failed
                last = e
                self.notebook.append({"step": step, "backend": self.backend, "attempt": attempt, "error": str(e)[:300]})
        raise RuntimeError(f"{step}: {last}")

    def _codex(self, system, prompt, schema, max_tokens, images=None):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            sp, op = Path(d) / "schema.json", Path(d) / "answer.json"
            sp.write_text(json.dumps(schema))
            full = f"{system}\n\n---\n\n{prompt}\n\nОтветь только JSON по схеме. Не используй инструменты и файлы."
            r = subprocess.run(["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "-C", d,
                                "--output-schema", str(sp), "-o", str(op),
                                *[a for i in images or [] for a in ("-i", str(Path(i).resolve()))], "--", full],
                               capture_output=True, text=True, timeout=3600, stdin=subprocess.DEVNULL)
            if not op.exists():
                raise RuntimeError(f"codex: {r.stderr[-400:]}")
            return op.read_text(), {"engine": "codex-cli"}

    def _claude(self, system, prompt, schema, max_tokens):
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(["claude", "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
                                "--system-prompt", system, "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch",
                                prompt], capture_output=True, text=True, timeout=3600, cwd=d, stdin=subprocess.DEVNULL)
            data = json.loads(r.stdout)
            out = data.get("structured_output") or data.get("result")
            text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
            return text, {"engine": "claude-code", "cost_usd": data.get("total_cost_usd")}

    def _api(self, system, prompt, schema, max_tokens):
        with self.client.beta.messages.stream(
            model=MODEL,
            max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason == "refusal":
            raise RuntimeError(f"refused ({msg.stop_details})")
        u = msg.usage
        return next(b.text for b in msg.content if b.type == "text"), {"engine": msg.model, "usage": {
            "input": u.input_tokens, "output": u.output_tokens,
            "cache_read": u.cache_read_input_tokens, "cache_write": u.cache_creation_input_tokens}}


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
                if "properties" in node:
                    node["required"] = list(node["properties"])
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)

    close(s)
    for d in s.get("$defs", {}).values():
        close(d)
    # A free-form mapping of functions to scenes stays open.
    for name in ("skeleton_mapping",):
        if name in s.get("properties", {}):
            s["properties"][name] = {"type": "object", "additionalProperties": {"type": "string"}}
    return s


def frame(p: dict) -> str:
    m, a, w = p["_m"], p["_a"], p["_w"]
    ex = exemplars(a["id"])
    parts = [
        "Ты — писатель. Ты пишешь по-русски, живой прозой, без штампов.",
        "Ты никогда не упоминаешь технику, компьютеры, серверы, сети, программы. Мир задан ниже и не обсуждается.",
        f"МЕТОД: {m['name']}. " + "; ".join(f"{k}: {v}" for k, v in m.items() if k not in ("id", "name")),
        f"УЧИТЕЛЬ ЯЗЫКА: {a['name']}. Приёмы: {', '.join(a['devices'])}. Язык: {a['language']}.",
        f"МИР: {w['label']}. Детали мира: {'; '.join(w['details'])}.",
    ]
    if ex:
        parts.append("ОБРАЗЦЫ ЯЗЫКА (не цитировать, писать так же):\n\n" + "\n\n---\n\n".join(ex))
    return "\n\n".join(parts)


def write_story(material: dict, catalogue: list[dict], out: Path, k_points: int = 3, scene_variants: int = 2) -> dict:
    nb: list = []
    stem = f"{material['cluster']}_{material['window'].replace(':', '_')}"
    seed = int.from_bytes(hashlib.sha256(stem.encode()).digest()[:4], "big")
    pts = points(material, catalogue, k_points, seed)
    sk = skeleton_ru(material)
    w = Writer(nb)
    nb.append({"step": "points", "chosen": [{k: v for k, v in p.items() if not k.startswith("_")} for p in pts],
               "skeleton": sk})
    syns = []
    for p in pts:
        prompt = ("Скелет истории (функции по порядку, с весом):\n" + json.dumps(sk, ensure_ascii=False) +
                  "\n\nПридумай рассказ на 3–5 тысяч слов в заданном мире и методе, который реализует ровно эти функции. "
                  "Персонажам дай желание и страх. Дай 10–15 конкретных деталей мира. В поле diary — короткая заметка "
                  "от первого лица: почему ты выбрал такую историю.")
        syns.append((p, w.ask(frame(p), prompt, Synopsis, f"synopsis:{p['method']}:{p['author']}:{p['world']}")))
    judge = ("Ты — редактор и критик. Выбери лучший синопсис по силе замысла, человеческим ставкам, верности методу "
             "и скелету, отсутствию штампов. Верни индекс (с нуля).")
    listing = "\n\n".join(f"[{i}] {s.title}\n{s.synopsis}\nФинал: {s.ending}" for i, (_, s) in enumerate(syns))
    v = w.ask(judge, listing, Verdict, "verdict:synopsis", max_tokens=8000)
    p, syn = syns[v.best]
    sys_ = frame(p) + "\n\nКАНОН ИСТОРИИ:\n" + syn.model_dump_json()
    plan = w.ask(sys_, "Разбей историю на 6–10 сцен. Каждая функция скелета — минимум одна сцена. Каждая сцена держится на конкретной детали.",
                 Plan, "plan")
    texts = []
    for i, sc in enumerate(plan.scenes):
        prev = "\n\n".join(texts[-2:])
        variants = []
        for j in range(scene_variants):
            prompt = (f"Предыдущие сцены (для связности):\n{prev}\n\nНапиши сцену {i + 1} из {len(plan.scenes)}:\n"
                      f"{sc.model_dump_json()}\n\nТолько текст сцены, 400–700 слов.")
            variants.append(w.ask(sys_, prompt, SceneText, f"scene:{i}:{j}", max_tokens=16000).text)
        if len(variants) > 1:
            vv = w.ask("Ты — редактор. Выбери лучший вариант сцены: язык, деталь, верность канону.",
                       "\n\n".join(f"[{j}]\n{t}" for j, t in enumerate(variants)), Verdict, f"verdict:scene:{i}", max_tokens=8000)
            texts.append(variants[vv.best])
        else:
            texts.append(variants[0])
    draft = "\n\n".join(texts)
    for k, task in enumerate([
        "Пройди по тексту как редактор: убери штампы, повторы, пустые эпитеты, гладкие концовки абзацев. Сохрани голос.",
        "Сверь текст с каноном: имена, возраст, предметы, последовательность. Исправь противоречия. Сделай финал менее гладким, если он гладкий.",
    ]):
        e = w.ask(sys_, f"{task}\n\nТЕКСТ:\n{draft}", Edit, f"edit:{k}", max_tokens=48000)
        draft = e.text
    leaks = [x for x in FORBIDDEN_WORDS if x in draft.lower()]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.md").write_text(f"# {syn.title}\n\n{draft}\n")
    rec = {"material": material["window"], "cluster": material["cluster"], "title": syn.title,
           "method": p["method"], "author": p["author"], "world": p["world"],
           "words": len(draft.split()), "technical_leaks": leaks,
           "key": {"skeleton": sk, "mapping": syn.skeleton_mapping}, "notebook": nb}
    (out / f"{stem}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    return {k: rec[k] for k in ("title", "method", "author", "world", "words", "technical_leaks")}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("materials", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/works/literature"))
    a = ap.parse_args()
    catalogue: list[dict] = []
    for p in a.materials:
        r = write_story(json.loads(p.read_text()), catalogue, a.out)
        catalogue.append(r)
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
