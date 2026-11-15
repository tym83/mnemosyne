"""The Lexicon of the atelier: a dictionary in the manner of Pavić, with one version and one book.

Its entries are the entities of the atelier's history: creators, works, schools,
critics, the places, things and figures that live in the works, and the events
of the Lives. Entities are joined by typed relations. Everything that is
structure is deterministic code:

- entities and relations are read from the lineage (catalogues, teachers,
  influences, schools, reviews, events) and from the notebooks;
- linking is an alias index: a name in any text points to its entry, with
  Russian case endings, without a model; an alias two entities share links
  to neither;
- every paragraph of an entry has a fixed set of primary sources (works,
  notebooks, reviews, Lives chapters, school poetics), cited by id; it is
  rewritten only when the digest of those sources changes;
- a revision makes a new edition of the entry, and the old editions stay.

Only two things are written by a model (literature.Writer, role chronicler):
the prose of a paragraph from its sources, and the places, things and figures
named in a literary work's text, asked once per version of that text.

The Lexicon lives in lexicon.json beside lineage.json. The life loop calls
update(life, base) from time to time; each call spends at most `limit` model
calls, new entries first, so the dictionary catches up over several calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Literal

from pydantic import BaseModel

from .weave.variants import plain

FILE = 'lexicon.json'
VERSION = 1

TYPES = {'creator': 'творец', 'work': 'работа', 'school': 'школа', 'critic': 'критик', 'place': 'место',
         'thing': 'вещь', 'figure': 'лицо из работ', 'event': 'событие'}
PROPER = {'creator', 'critic', 'figure'}   # names of persons: linked only when written with a capital
# Events that make an entry of their own; the rest of a life is told in the creator's entry.
EVENT_KINDS = ('school_birth', 'death', 'master', 'period', 'rediscovery', 'return', 'renounce', 'surpassed',
               'first_accepted', 'last_work', 'secret_miracle')
# Lives chapters that tell a life; reviews and encounters belong to other paragraphs.
LIFE_SKIP = ('review', 'essay', 'encounter', 'verification')
TOPICS = {'life': 'Жизнь', 'works': 'Работы', 'reception': 'Отклик', 'work': 'Вещь', 'poetics': 'Поэтика',
          'practice': 'Школа в мастерской', 'writings': 'Что писал', 'event': 'Событие',
          'appearances': 'Где встречается'}
OUT = {'author_of': 'автор работы', 'in_school': 'школа', 'member_of': 'работал(а) в школе',
       'student_of': 'ученик(ца)', 'founded': 'основал(а) школу', 'influenced': 'повлиял(а) на',
       'reviewed': 'писал(а) о работе', 'wrote_about': 'писал(а) о', 'concerns': 'касается',
       'appears_in': 'есть в работе', 'mentions': 'упоминает'}
IN = {'author_of': 'автор', 'in_school': 'работы школы', 'member_of': 'творцы школы', 'student_of': 'учитель для',
      'founded': 'основатель', 'influenced': 'испытал(а) влияние', 'reviewed': 'о ней писали',
      'wrote_about': 'о нём писали', 'concerns': 'события', 'appears_in': 'места, вещи и лица',
      'mentions': 'упомянут(а) в'}

SYSTEM = ('Ты — составитель Словаря мастерской, словаря в духе «Хазарского словаря» Павича: статья — связный '
          'рассказ, а не справка, с живой деталью и памятью о других статьях. Но версия у словаря одна: никаких '
          'расходящихся преданий, трёх книг и выдуманных свидетелей. Пиши по-русски, один абзац, только о том, '
          'что есть в источниках; чего нет в источниках — нет и в статье. После утверждения ставь в квадратных '
          'скобках id источника, из которого оно взято, например [work:a-w00001]. Цитаты из текстов на другом '
          'языке давай в оригинале и в переводе. Не упоминай ночи, номера, технику и мастерскую как механизм.')


class Paragraph(BaseModel):
    text: str


class Thing(BaseModel):
    name: str
    kind: Literal['place', 'thing', 'figure']
    aliases: list[str]
    gloss: str


class Things(BaseModel):
    items: list[Thing]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ---------------------------------------------------------------- persistence

def empty() -> dict:
    return {'version': VERSION, 'entries': {}, 'sources': {}, 'extracted': {}, 'updated': None}


def load(base) -> dict:
    path = Path(base)/FILE
    if not path.exists():
        return empty()
    data = json.loads(path.read_text())
    if data.get('version') != VERSION:
        raise ValueError('unsupported lexicon version')
    return {**empty(), **data}


def save(base, lex: dict):
    path = Path(base)/FILE
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(lex, ensure_ascii=False, indent=1))
    tmp.replace(path)


# ---------------------------------------------------------------- primary sources

def name_of(a) -> str:
    return a.name if a.name != a.id else 'творец'


def flatten(value) -> list[str]:
    if isinstance(value, str):
        return [plain(value)] if value.strip() else []
    if isinstance(value, list):
        return [x for v in value for x in flatten(v)]
    if isinstance(value, dict):
        return [x for v in value.values() for x in flatten(v)]
    return []


def notebooks(life, base) -> dict:
    """Every notebook by its work: the session files, and the composer's notebook kept in the work."""
    found = {}
    if base is not None and Path(base).is_dir():
        for p in sorted(Path(base).rglob('notebook.json')):
            try:
                record = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(record, dict) and record.get('opus'):
                found[record['opus']] = record
    for a in life.artists:
        for w in a.catalogue:
            record = (w.get('process') or {}).get('composer')
            if isinstance(record, dict) and record.get('opus'):
                found.setdefault(record['opus'], record)
    return found


def school_title(key) -> str:
    from .writing import poetics
    p = poetics.load(key)
    if p and p.get('name'):
        return p['name']
    from .viewer import SCHOOL_RU
    return SCHOOL_RU.get(key, (key, ''))[0]


def sources(life, base=None) -> dict:
    """The primary sources by id: kind, title, owner and text. Their digests decide what is stale."""
    from .writing import memory, poetics
    out = {}

    def add(sid, kind, title, text, **meta):
        text = text.strip()
        if text:
            out[sid] = {'kind': kind, 'title': title, 'text': text, 'digest': digest(text), **meta}

    for a in life.artists:
        for w in a.catalogue:
            if w.get('synthetic'):
                continue
            body = '\n\n'.join(x for x in (w.get('title') and f'«{w["title"]}»', w.get('idea') and plain(w['idea']),
                                            plain(w.get('text') or w.get('excerpt') or '')) if x)
            add(f'work:{w["id"]}', 'work', w.get('title') or w['id'], body, artist=a.id, work=w['id'],
                school=w.get('school'))
        for c in life.biographies[a.id].chapters:
            if c.get('kind') in LIFE_SKIP:
                continue
            words = [v for k, v in (c.get('words') or {}).items() if k in ('diary', 'letter', 'image') and v]
            add(f'lives:{c["event"]}', 'lives', f'Жизнеописание: {name_of(a)}, {c.get("date", "")[:10]}',
                '\n'.join([c.get('text') or ''] + [plain(x) for x in words]), artist=a.id, event=c['event'])
    for opus, record in notebooks(life, base).items():
        add(f'notebook:{opus}', 'notebook', f'Блокнот: {opus}', '\n'.join(flatten(memory.prose(record))),
            artist=record.get('artist'), work=opus)
    critics = {c['id']: c['name'] for c in life.reception.critics}
    for r in life.reception.reviews:
        if r.get('text') and not r.get('words_pending'):
            add(f'review:{r["id"]}', 'review', f'{critics.get(r["critic"], r["critic"])}: {r.get("about") or r.get("kind")}',
                plain(r['text']), critic=r['critic'], work=r.get('work'), artist=r.get('artist'),
                subject=r.get('subject'), genre=r.get('kind', 'work'))
    for key in sorted(used_schools(life)):
        record = life.schools.get(key) or {}
        text = poetics.full(key) if poetics.load(key) else '\n'.join(
            flatten(record.get('manifesto') or {}) + [record.get('name', '')])
        add(f'school:{key}', 'school', school_title(key), text, school=key)
    return out


def person(name: str) -> list[str]:
    """A person is named in full and by surname; a surname two people share links to neither."""
    words = name.split()
    return [name] + ([words[-1]] if len(words) > 1 and len(words[-1]) >= 4 else [])


def used_schools(life) -> set:
    keys = {w.get('school') for a in life.artists for w in a.catalogue if not w.get('synthetic') and w.get('school')}
    return {k for k in keys | set(life.schools) if k and 'tradition' not in k}


# ---------------------------------------------------------------- entities and relations

def thing_id(kind, name) -> str:
    return f'{kind}:{hashlib.sha256(norm(name).encode()).hexdigest()[:10]}'


def entities(life, src: dict, extracted: dict | None = None) -> dict:
    """Every entity with its name, aliases and paragraphs, each paragraph with its source ids."""
    by_kind = {}
    for sid, s in src.items():
        by_kind.setdefault(s['kind'], []).append(sid)
    of = lambda kind, **match: sorted(sid for sid in by_kind.get(kind, [])
                                      if all(src[sid].get(k) == v for k, v in match.items()))
    out = {}

    def entity(eid, etype, name, aliases, paragraphs, **facts):
        paragraphs = [(t, ids) for t, ids in paragraphs if ids]
        if paragraphs:
            out[eid] = {'type': etype, 'name': name, 'aliases': sorted({a for a in aliases if a}),
                        'paragraphs': paragraphs, 'facts': facts}

    live = {w['id'] for a in life.artists for w in a.catalogue if not w.get('synthetic')}
    for a in life.artists:
        works = [w for w in a.catalogue if w['id'] in live]
        about = sorted(sid for sid in by_kind.get('review', []) if src[sid].get('artist') == a.id
                       or src[sid].get('work') in {w['id'] for w in works})
        entity(f'creator:{a.id}', 'creator', name_of(a) if a.name != a.id else a.id,
               person(a.name) if a.name != a.id else [],
               [('life', of('lives', artist=a.id)),
                ('works', sorted(of('work', artist=a.id) + [f'notebook:{w["id"]}' for w in works
                                                            if f'notebook:{w["id"]}' in src])),
                ('reception', about)], art=a.art, language=a.language, status=a.status)
        for w in works:
            entity(f'work:{w["id"]}', 'work', w.get('title') or plain(w.get('idea') or '')[:60] or w['id'],
                   [w.get('title')],
                   [('work', [s for s in (f'work:{w["id"]}', f'notebook:{w["id"]}') if s in src]),
                    ('reception', of('review', work=w['id']))], artist=a.id, school=w.get('school'))
    for key in sorted(used_schools(life)):
        name = school_title(key)
        entity(f'school:{key}', 'school', name, [name],
               [('poetics', [f'school:{key}'] if f'school:{key}' in src else []),
                ('practice', of('work', school=key)),
                ('reception', sorted(sid for sid in by_kind.get('review', [])
                                     if src[sid].get('genre') in ('manifesto', 'school')
                                     and src[sid].get('subject') in (key, (life.schools.get(key) or {}).get('name'))))],
               school=key)
    for c in life.reception.critics:
        entity(f'critic:{c["id"]}', 'critic', c['name'], [c['name']], [('writings', of('review', critic=c['id']))],
               voice=c.get('voice'))
    from .chronicle import KINDS, agree
    artists = {a.id: a for a in life.artists}
    for e in life.events:
        a = artists.get(e['artist'])
        if e['kind'] not in EVENT_KINDS or a is None:
            continue
        ids = [f'lives:{e["id"]}'] + ([f'work:{e["facts"]["work"]}'] if f'work:{e["facts"].get("work")}' in src else [])
        entity(f'event:{e["id"]}', 'event', agree(f'{KINDS.get(e["kind"], e["kind"])}: {name_of(a)}', a) +
               f', {e["date"][:10]}', [], [('event', [i for i in ids if i in src])],
               artist=a.id, event=e['kind'], date=e['date'], work=e['facts'].get('work'))
    things = {}
    for wid, x in sorted((extracted or {}).items()):
        if f'work:{wid}' not in src:
            continue
        for item in x.get('items', []):
            eid = thing_id(item['kind'], item['name'])
            t = things.setdefault(eid, {'kind': item['kind'], 'name': item['name'], 'aliases': set(), 'works': set(),
                                        'gloss': item.get('gloss', '')})
            t['aliases'] |= {item['name'], *item.get('aliases', [])}
            t['works'].add(wid)
    for eid, t in things.items():
        entity(eid, t['kind'], t['name'], t['aliases'], [('appearances', sorted(f'work:{w}' for w in t['works']))],
               gloss=t['gloss'], works=sorted(t['works']))
    return out


def owner(sid: str, src: dict, ents: dict) -> str | None:
    """The entity whose own words a source is: a work, a critic, a creator, a school."""
    s = src[sid]
    candidates = {'work': [f'work:{s.get("work")}'], 'notebook': [f'work:{s.get("work")}', f'creator:{s.get("artist")}'],
                  'review': [f'critic:{s.get("critic")}'], 'lives': [f'creator:{s.get("artist")}'],
                  'school': [f'school:{s.get("school")}']}.get(s['kind'], [])
    return next((c for c in candidates if c in ents), None)


def relations(life, ents: dict, src: dict, index: 'Index') -> list[dict]:
    rels = set()

    def rel(kind, a, b, source=None):
        if a in ents and b in ents and a != b:
            rels.add((kind, a, b, source or ''))

    for a in life.artists:
        for t in a.teachers:
            rel('student_of', f'creator:{a.id}', f'creator:{t}')
        for w in a.catalogue:
            rel('author_of', f'creator:{a.id}', f'work:{w["id"]}')
            if w.get('school'):
                rel('in_school', f'work:{w["id"]}', f'school:{w["school"]}')
                if f'work:{w["id"]}' in ents:
                    rel('member_of', f'creator:{a.id}', f'school:{w["school"]}')
    for key, record in life.schools.items():
        rel('founded', f'creator:{record.get("author")}', f'school:{key}')
    for e in life.influences:
        rel('influenced', f'creator:{e["source"]}', f'creator:{e["target"]}', e.get('work') and f'work:{e["work"]}')
    for sid, s in src.items():
        if s['kind'] == 'review':
            if s.get('work'):
                rel('reviewed', f'critic:{s["critic"]}', f'work:{s["work"]}', sid)
            elif s.get('genre') in ('manifesto', 'school'):
                rel('wrote_about', f'critic:{s["critic"]}', f'school:{s.get("subject")}', sid)
            else:
                rel('wrote_about', f'critic:{s["critic"]}', f'creator:{s.get("artist")}', sid)
    for eid, e in ents.items():
        if e['type'] == 'event':
            rel('concerns', eid, f'creator:{e["facts"]["artist"]}', f'lives:{eid.split(":", 1)[1]}')
            if e['facts'].get('work'):
                rel('concerns', eid, f'work:{e["facts"]["work"]}')
        if e['type'] in ('place', 'thing', 'figure'):
            for wid in e['facts']['works']:
                rel('appears_in', eid, f'work:{wid}', f'work:{wid}')
    # Mentions: a name found by the alias index in someone's own words.
    for sid in sorted(src):
        who = owner(sid, src, ents)
        if who is None:
            continue
        for _, _, eid in index.link(src[sid]['text']):
            rel('mentions', who, eid, sid)
    return [{'type': k, 'from': a, 'to': b, **({'source': s} if s else {})} for k, a, b, s in sorted(rels)]


# ---------------------------------------------------------------- the alias index

ENDINGS = '(?:а|я|у|ю|ом|ем|ой|ей|е|и|ы|ам|ям|ами|ями|ах|ях|ою|ею|ов|ев|ь)?'
SOFT = 'аяоеыиуюйь'
QUOTES = '«»„“”"\''


def norm(text: str) -> str:
    return ' '.join(re.findall(r'\w+', text.casefold().replace('ё', 'е')))


def pattern(alias: str) -> str | None:
    """A regular expression for an alias with Russian case endings on its Cyrillic words."""
    words = re.findall(r'\w+', alias.replace('ё', 'е').replace('Ё', 'Е'))
    if sum(len(w) for w in words) < 4:
        return None
    parts = []
    for w in words:
        if re.fullmatch(r'[а-яА-Я]+', w) and len(w) >= 4:
            stem = w[:-1] if w[-1].lower() in SOFT else w
            parts.append(re.escape(stem) + ENDINGS)
        else:
            parts.append(re.escape(w))
    return r'(?<!\w)' + r'\W+'.join(parts) + r'(?!\w)'


class Index:
    """Names to entries. Deterministic: longest match wins, a shared alias points nowhere."""

    def __init__(self, ents: dict):
        owners = {}
        for eid, e in ents.items():
            for alias in e.get('aliases', []):
                owners.setdefault(norm(alias), {})[eid] = alias
        self.patterns = []
        for key, who in sorted(owners.items()):
            if len(who) != 1:
                continue
            (eid, alias), = who.items()
            p = pattern(alias)
            if p:
                proper = ents[eid]['type'] in PROPER and alias[:1].isupper()
                probe = norm(alias)[:3]
                self.patterns.append((re.compile(p, re.IGNORECASE), eid, proper, probe, len(key)))
        self.patterns.sort(key=lambda x: (-x[4], x[1]))

    def link(self, text: str) -> list[tuple[int, int, str]]:
        """(start, end, entity id) for every name in the text, without overlaps, in order."""
        if not text:
            return []
        low = text.replace('ё', 'е').replace('Ё', 'Е')
        folded = low.casefold()
        found = []
        for rx, eid, proper, probe, size in self.patterns:
            if probe not in folded:
                continue
            for m in rx.finditer(low):
                if proper and not text[m.start()].isupper():
                    continue
                found.append((m.start(), m.end(), eid))
        found.sort(key=lambda x: (-(x[1] - x[0]), x[0], x[2]))
        taken, out = [], []
        for s, e, eid in found:
            if all(e <= a or s >= b for a, b in taken):
                taken.append((s, e))
                out.append((s, e, eid))
        return sorted(out)

    @classmethod
    def of_entries(cls, entries: dict) -> 'Index':
        return cls({eid: {'type': e['type'], 'aliases': e.get('aliases', [])} for eid, e in entries.items()})


# ---------------------------------------------------------------- writing

CITE = re.compile(r'\[([a-z]+:[^\[\]\s,;]+)\]')


def clean(text: str, allowed) -> str:
    """Prose without variants and without citations of sources the paragraph does not have."""
    allowed = set(allowed)
    return CITE.sub(lambda m: m.group(0) if m.group(1) in allowed else '', plain(text)).replace(' .', '.').strip()


def ask(writer_factory, system, prompt, schema, step):
    from .literature import DRAFTING, LANGUAGE
    drafting, spoken = DRAFTING.set(False), LANGUAGE.set(None)
    try:
        return writer_factory([]).ask(system, prompt, schema, step)
    finally:
        LANGUAGE.reset(spoken)
        DRAFTING.reset(drafting)


def paragraph_prompt(eid, e, topic, ids, src, related, russian) -> str:
    lines = [f'Статья: «{e["name"]}» ({TYPES.get(e["type"], e["type"])}). Абзац: {TOPICS.get(topic, topic)}.']
    if e['facts'].get('gloss'):
        lines.append(f'Что это: {e["facts"]["gloss"]}')
    if related:
        lines.append('Связанные статьи словаря (называй их так, как они названы): ' + '; '.join(related))
    budget = 16000
    for sid in ids:
        s = src[sid]
        text = s['text'][:max(0, min(4000, budget))]
        budget -= len(text)
        lines.append(f'\n[{sid}] {s["title"]}\n{text}')
        ru = russian(s['text'])
        if ru and ru != s['text']:
            lines.append(f'Перевод Переводчика: {plain(ru)[:2000]}')
        if budget <= 0:
            break
    lines.append('\nНапиши абзац этой статьи по этим источникам, со ссылками на их id.')
    return '\n'.join(lines)


def extract(writer_factory, wid, s) -> list[dict]:
    things = ask(writer_factory, 'Ты — составитель Словаря мастерской. Назови места, вещи и лица, которые есть в '
                 'этом тексте: только названное в самом тексте, не автора и не школу, не больше восьми, самое '
                 'значимое для вещи. name — как в тексте, в начальной форме; aliases — другие формы и имена, как '
                 'они написаны в тексте; gloss — одна фраза по-русски: что это в этой вещи. kind: place, thing или '
                 'figure.', s['text'][:12000], Things, f'lexicon:things:{wid}')
    return [t.model_dump() for t in things.items[:8] if t.name.strip()]


def update(life, base, *, writer_factory: Callable | None = None, limit: int = 40, log=None) -> dict:
    """Bring the Lexicon up to date with the atelier. Deterministic except the prose and the things asked.

    At most `limit` model calls: works not yet read for their things first, then entries never
    written, then stale ones. An entry is revised as a whole edition only when every stale
    paragraph of it was written; otherwise it waits for the next call.
    """
    if writer_factory is None:
        from .literature import Writer
        writer_factory = lambda nb: Writer(nb, role='chronicler', data_class='art')
    say = log or (lambda *_: None)
    base = Path(base)
    lex = load(base)
    from .writing.memory import Memory
    memory = Memory(base)
    russian = lambda text: memory.get(text)
    src = sources(life, base)
    calls, errors = 0, []
    literary = {a.id for a in life.artists if a.art == 'literature'}
    for sid in sorted(src):
        s = src[sid]
        if s['kind'] != 'work' or s.get('artist') not in literary:
            continue
        wid = s['work']
        if lex['extracted'].get(wid, {}).get('digest') == s['digest'] or calls >= limit:
            continue
        calls += 1
        try:
            lex['extracted'][wid] = {'digest': s['digest'], 'items': extract(writer_factory, wid, s), 'at': now()}
        except Exception as exc:
            errors.append(f'{sid}: {type(exc).__name__}: {exc}'[:300])
    ents = entities(life, src, lex['extracted'])
    index = Index(ents)
    rels = relations(life, ents, src, index)
    touching = {}
    for r in rels:
        touching.setdefault(r['from'], []).append(r)
        touching.setdefault(r['to'], []).append(r)
    lex['sources'] = {sid: {k: v for k, v in s.items() if k != 'text'} for sid, s in src.items()}
    stamp, revised = now(), []
    for eid, e in ents.items():
        entry = lex['entries'].setdefault(eid, {'id': eid, 'edition': 0, 'paragraphs': [], 'editions': []})
        # Structure is always current; only prose waits for its sources.
        entry.update(type=e['type'], name=e['name'], aliases=e['aliases'], facts=e['facts'],
                     relations=touching.get(eid, []), gone=False,
                     sources=sorted({sid for _, ids in e['paragraphs'] for sid in ids}))
    for eid in lex['entries']:
        if eid not in ents:
            lex['entries'][eid]['gone'] = True

    def stale(eid):
        current = {p['topic']: p for p in lex['entries'][eid]['paragraphs']}
        wanted = [(t, ids, digest([[i, src[i]['digest']] for i in ids])) for t, ids in ents[eid]['paragraphs']]
        return wanted, [t for t, _, d in wanted if current.get(t, {}).get('digest') != d] + \
            [t for t in current if t not in {w[0] for w in wanted}]

    order = sorted(ents, key=lambda eid: (lex['entries'][eid]['edition'] > 0, eid))
    pending = 0
    for eid in order:
        wanted, changed = stale(eid)
        if not changed:
            continue
        writes = [t for t, _, _ in wanted if t in changed]
        if calls + len(writes) > limit:
            pending += 1
            continue
        entry, e = lex['entries'][eid], ents[eid]
        old = {p['topic']: p for p in entry['paragraphs']}
        names = {r['to'] if r['from'] == eid else r['from'] for r in entry['relations']}
        related = sorted({f'{ents[n]["name"]} ({TYPES[ents[n]["type"]]})' for n in names if n in ents})[:24]
        paragraphs, failed = [], False
        for topic, ids, d in wanted:
            if topic not in changed:
                paragraphs.append(old[topic])
                continue
            calls += 1
            try:
                words = ask(writer_factory, SYSTEM, paragraph_prompt(eid, e, topic, ids, src, related, russian),
                            Paragraph, f'lexicon:{eid}:{topic}')
            except Exception as exc:
                errors.append(f'{eid}/{topic}: {type(exc).__name__}: {exc}'[:300])
                failed = True
                break
            paragraphs.append({'topic': topic, 'text': clean(words.text, ids), 'sources': ids, 'digest': d,
                               'written': stamp, 'edition': entry['edition'] + 1,
                               'source_digests': {i: src[i]['digest'] for i in ids}})
        if failed:
            pending += 1
            continue
        if entry['paragraphs']:
            # The old edition stays: a dictionary remembers what it used to say.
            entry['editions'].append({'edition': entry['edition'], 'date': entry.get('revised'),
                                      'night': entry.get('night'), 'paragraphs': entry['paragraphs']})
        entry.update(paragraphs=paragraphs, edition=entry['edition'] + 1, revised=stamp, night=life.night)
        revised.append(eid)
        say('lexicon revised', eid, entry['edition'])
    lex['updated'] = stamp
    if errors:
        lex['errors'] = errors[-20:]
    save(base, lex)
    return {'entities': len(ents), 'relations': len(rels), 'revised': revised, 'pending': pending,
            'calls': calls, 'errors': errors}
