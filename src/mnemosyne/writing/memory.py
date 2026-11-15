"""The Translator's memory: Russian renderings of everything in an atelier that is not Russian.

Works, drafts, ideas, diaries, the inner critic's reasons, portraits, Lives
chapters and reviews are written in the creators' mother tongues; so are a
composer's notebooks: the idea, its interrogation, the method in words, the
halftones and the composer's own listening to each sketch and draft. The Translator
walks the atelier after the nights, renders what is foreign and keeps it in
translations.json at the atelier root, keyed by the text. Nothing in the
atelier itself changes; the viewer shows the Russian with the original beside it.

  mnemo translate --root DIR
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from pydantic import BaseModel

from ..literature import DRAFTING, LANGUAGE, Writer
from ..weave.variants import plain
from . import translator

FILE = 'translations.json'
LONG = 1200
BATCH = 4


class Batch(BaseModel):
    items: list[str]


def key(text: str) -> str:
    return hashlib.sha256(plain(text).strip().encode()).hexdigest()[:24]


def foreign(text) -> bool:
    """True for prose that is mostly not Cyrillic: the Translator should render it."""
    if not isinstance(text, str):
        return False
    letters = re.findall(r'[^\W\d_]', plain(text))
    if len(letters) < 12:
        return False
    return sum('а' <= c.lower() <= 'я' or c.lower() == 'ё' for c in letters) / len(letters) < .5


class Memory:
    def __init__(self, root: Path):
        self.path = Path(root)/FILE
        self.items = json.loads(self.path.read_text()) if self.path.exists() else {}

    def get(self, text):
        return self.items.get(key(text)) if isinstance(text, str) else None

    def put(self, text, russian):
        self.items[key(text)] = russian

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1))
        tmp.replace(self.path)


NOTEBOOK_FIELDS = ('statement', 'interrogation', 'method', 'drafts', 'verdict', 'portrait', 'plan', 'idea')
# A composer's method in words; the rest of it (school codes, sources, NotaGen prompt) is not prose.
COMPOSER_METHOD = ('principle', 'transformation', 'concept', 'reason')


def composer(record) -> bool:
    """A composer's notebook: writers' notebooks say art=literature, composers' keep sketches."""
    return isinstance(record, dict) and record.get('art') != 'literature' and \
        ('sketches' in record or record.get('art') == 'music')


def hearings(record) -> list[dict]:
    """The composer's own listening to each sketch and draft, last answer per step, in order."""
    out = {}
    for e in record.get('entries') or []:
        if isinstance(e, dict) and str(e.get('step', '')).startswith('listen:') and isinstance(e.get('result'), dict):
            out[e['step']] = {'step': e['step'], **e['result']}
    return list(out.values())


def prose(record) -> dict:
    """The parts of a notebook a reader reads, for the Translator: per art, only words, never plans."""
    if not composer(record):
        return {k: record.get(k) for k in NOTEBOOK_FIELDS}
    method = record.get('method') or {}
    verdict = record.get('verdict') or {}
    return {'statement': record.get('statement'), 'interrogation': record.get('interrogation'),
            'portrait': record.get('portrait'), 'method': {k: method.get(k) for k in COMPOSER_METHOD},
            'halftones': record.get('halftones'),
            'hearings': [{k: h.get(k) for k in ('reasons', 'corrections')} for h in hearings(record)],
            'verdict': {k: verdict.get(k) for k in ('reasons', 'corrections')},
            'let_go': (record.get('let_go') or {}).get('left_undone')}
SKIP = {'id', 'kind', 'school', 'verdict', 'opus', 'artist', 'step', 'backend', 'engine', 'status'}


def strings(value, out):
    if isinstance(value, str):
        if foreign(value):
            out.append(value)
    elif isinstance(value, list):
        for v in value:
            strings(v, out)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in SKIP or isinstance(v, (dict, list)):
                strings(v, out)


def gather(root: Path) -> list[str]:
    """Every foreign text the viewer shows, in a stable order without repeats."""
    root, out = Path(root), []
    life = json.loads((root/'lineage.json').read_text())
    for a in life['artists']:
        strings([a.get('portrait'), [w.get('idea') for w in a.get('catalogue', [])]], out)
        # A composer's notebook also lives in the work itself: it outlasts the files of the night.
        for w in a.get('catalogue', []):
            record = (w.get('process') or {}).get('composer')
            if isinstance(record, dict):
                strings(prose(record), out)
    for chapters in life.get('biographies', {}).values():
        strings([c.get('text') for c in chapters.get('chapters', [])], out)
    strings([r.get('text') for r in life.get('reception', {}).get('reviews', [])], out)
    strings([s.get('proposal') for s in life.get('school_attempts', [])], out)
    strings(list(life.get('schools', {}).values()), out)
    nights = root/'nights' if (root/'nights').is_dir() else root  # a lived history, or a studio volume
    for p in sorted(nights.rglob('*.txt')):
        if not p.name.endswith('.ru.txt'):
            strings(p.read_text(), out)
    for p in sorted(nights.rglob('notebook.json')):
        strings(prose(json.loads(p.read_text())), out)
    seen, unique = set(), []
    for text in out:
        if key(text) not in seen:
            seen.add(key(text))
            unique.append(text)
    return unique


def render_batch(texts, notebook, backend):
    writer = Writer(notebook, backend=backend, role='translator', data_class='art')
    drafting, spoken = DRAFTING.set(False), LANGUAGE.set(None)
    try:
        result = writer.ask(translator.SYSTEM + ' Тебе дан JSON-список фрагментов: переведи каждый, верни список '
                            'той же длины в том же порядке.', json.dumps([plain(t) for t in texts], ensure_ascii=False),
                            Batch, 'translate:batch').items
    finally:
        LANGUAGE.reset(spoken)
        DRAFTING.reset(drafting)
    if len(result) != len(texts):
        return [None] * len(texts)
    return [r if not translator.missing(plain(t), r) else None for t, r in zip(texts, result)]


def backfill(root: Path, *, backend=None, log=print) -> int:
    root, memory, notebook = Path(root), Memory(root), []
    todo = [t for t in gather(root) if memory.get(t) is None]
    log(f'{len(todo)} texts to translate')
    short = [t for t in todo if len(plain(t)) <= LONG]
    long = [t for t in todo if len(plain(t)) > LONG]
    done = 0

    def render(chunk):
        """A failed batch is halved and tried again; a single text that still fails goes the long way."""
        try:
            return list(zip(chunk, render_batch(chunk, notebook, backend)))
        except RuntimeError:
            reasons = [e.get('reason') for e in notebook if isinstance(e, dict) and e.get('reason')][-5:]
            (root/'translation-errors.json').write_text(json.dumps(reasons, ensure_ascii=False, indent=1))
            log(f'translate: a batch of {len(chunk)} failed: {reasons[-1:] or "no reason"}')
            if len(chunk) == 1:
                return [(chunk[0], None)]
            half = len(chunk) // 2
            return render(chunk[:half]) + render(chunk[half:])

    for i in range(0, len(short), BATCH):
        chunk = short[i:i + BATCH]
        for text, russian in render(chunk):
            if russian is None:
                long.append(text)
            else:
                memory.put(text, russian)
                done += 1
        memory.save()
        log(f'{done}/{len(todo)}')
    for text in long:
        # The Translator does not need to know the language: he names what he reads.
        try:
            memory.put(text, translator.translate(text, 'unknown', notebook, backend=backend, step='translate:long'))
        except RuntimeError:
            continue   # left for the next turn; the reason is in translation-errors.json
        done += 1
        memory.save()
        log(f'{done}/{len(todo)}')
    return done


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='mnemo translate')
    ap.add_argument('--root', type=Path, required=True, help='atelier directory with lineage.json and nights/')
    ap.add_argument('--backend')
    a = ap.parse_args(argv)
    backfill(a.root, backend=a.backend)
