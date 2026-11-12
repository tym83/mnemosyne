"""Read the atelier's history: from the console, or as a site anyone may browse.

The source is an atelier directory: lineage.json (the checkpoint) and the nights
with their works, notebooks, carriers and translations. Nothing here writes to
the atelier or the cluster; the site is a static export.

  mnemo view --root DIR artists | artist ID | work ID | lives ID | night N | timeline
  mnemo view --root DIR site --out SITE
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from .lineage import LANGUAGE_NAMES, Lineage
from .weave.variants import plain

ART = {'music': 'музыка', 'literature': 'литература'}


class Atelier:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.life = Lineage.restore(json.loads((self.root/'lineage.json').read_text()))
        self.nights = sorted((self.root/'nights').glob('[0-9][0-9][0-9]')) if (self.root/'nights').exists() else []
        self.year = [json.loads(l) for l in (self.root/'year.jsonl').read_text().splitlines()] \
            if (self.root/'year.jsonl').exists() else []

    def name(self, a):
        return a.id if a.name == a.id else a.name

    def artist(self, aid):
        return next(a for a in self.life.artists if a.id == aid)

    def works(self):
        for a in self.life.artists:
            for w in a.catalogue:
                yield a, w

    def work(self, wid):
        return next((a, w) for a, w in self.works() if w['id'] == wid)

    def files(self, wid):
        """Every file that belongs to a work: scores, texts, translations, notebooks, woven carriers."""
        return sorted(p for night in self.nights for p in night.rglob('*') if p.is_file() and wid in str(p))

    def notebook(self, wid):
        if not hasattr(self, '_notebooks'):
            self._notebooks = {}
            for night in self.nights:
                for p in night.rglob('notebook.json'):
                    record = json.loads(p.read_text())
                    if record.get('opus'):
                        self._notebooks[record['opus']] = record
        return self._notebooks.get(wid)

    def text(self, wid):
        texts = [p for p in self.files(wid) if p.suffix == '.txt' and not p.name.endswith('.ru.txt')]
        ru = [p for p in self.files(wid) if p.name.endswith('.ru.txt')]
        return (texts[0].read_text() if texts else None), (ru[0].read_text() if ru else None)

    def reviews(self, wid):
        return [r for r in self.life.reception.reviews if r['work'] == wid]


def show_artists(at):
    for a in at.life.artists:
        print(f'{a.id:14} {at.name(a)[:28]:28} {ART.get(a.art, a.art):10} {a.language:3} {a.status:8} '
              f'works {len(a.catalogue):3}  school {a.school}')


def show_artist(at, aid):
    a = at.artist(aid)
    print(f'{at.name(a)} ({a.id}) — {ART.get(a.art, a.art)}, язык: {LANGUAGE_NAMES.get(a.language, a.language)}')
    print(f'Родился {a.birth[:10]}, статус: {a.status}, школа: {a.school}, учителя: {", ".join(a.teachers) or "нет"}')
    if a.death:
        print(f'Умер {a.death[:10]}')
    print('\n' + (a.portrait or ''))
    print('\nРаботы:')
    for w in a.catalogue:
        print(f'  {w["id"]}  ночь {w["night"]:3}  {w["verdict"]:10} {"синтетическая" if w.get("synthetic") else "живая"}'
              f'  {w.get("school") or ""}  {(w.get("idea") or "")[:60]}')


def show_work(at, wid):
    a, w = at.work(wid)
    print(f'{wid} — {at.name(a)}, {ART.get(a.art, a.art)}, ночь {w["night"]}, вердикт {w["verdict"]}, школа {w.get("school")}')
    if w.get('idea'):
        print('\nЗамысел: ' + w['idea'])
    original, ru = at.text(wid)
    if original:
        print('\n' + original)
    if ru:
        print('\n— Перевод —\n' + ru)
    for r in at.reviews(wid):
        print(f'\nРецензия {r["critic"]} (ночь {r["night"]}, оценка {r["score"]:.2f}): {plain(r.get("text") or "")}')
    print('\nФайлы:')
    for p in at.files(wid):
        print('  ' + str(p))


def show_lives(at, aid):
    a = at.artist(aid)
    for c in at.life.biographies[aid].chapters:
        if c.get('text'):
            print(f'— ночь {c["night"]}, {c["kind"]} —\n{plain(c["text"])}\n')
        else:
            print(f'— ночь {c["night"]}, {c["kind"]} — (глава ещё не написана)')


def show_night(at, n):
    entry = next((y for y in at.year if y['night'] == n), None)
    if entry:
        print(json.dumps(entry, ensure_ascii=False, indent=1))
    root = at.root/'nights'/f'{n:03d}'
    if root.exists():
        for p in sorted(root.rglob('*')):
            if p.is_file():
                print('  ' + str(p.relative_to(at.root)))


def show_timeline(at):
    for e in at.life.events:
        a = next((x for x in at.life.artists if x.id == e['artist']), None)
        who = at.name(a) if a else e['artist']
        print(f'{e["date"][:10]}  ночь {e["night"]:3}  {who[:24]:24} {e["kind"]}')


# ---------------------------------------------------------------- the site

STYLE = """
:root{--bg:#fbfaf7;--fg:#1d1b18;--muted:#6b665e;--line:#e4dfd6;--accent:#7a3e2a}
@media (prefers-color-scheme:dark){:root{--bg:#161513;--fg:#ece8e1;--muted:#a29c92;--line:#2d2a26;--accent:#e0a183}}
body{background:var(--bg);color:var(--fg);font:17px/1.6 Georgia,'Times New Roman',serif;margin:0 auto;max-width:860px;padding:24px 16px}
a{color:var(--accent)}nav{font:14px system-ui,sans-serif;margin-bottom:24px}nav a{margin-right:14px}
h1,h2{font-weight:normal}pre{white-space:pre-wrap;font:inherit}.muted{color:var(--muted)}
table{border-collapse:collapse;width:100%;font:14px system-ui,sans-serif}td,th{border-bottom:1px solid var(--line);padding:6px 4px;text-align:left}
.work{border-top:1px solid var(--line);padding-top:16px;margin-top:24px}
.variants{color:var(--accent);font-size:.92em}
#score{background:#fff;border-radius:6px;padding:8px;overflow-x:auto}
"""
PLAYER = ('<script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,'
          'npm/focus-visible@5.2.0,npm/html-midi-player@1.5.0"></script>')
NOTATION = '<script src="https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.8.0/build/opensheetmusicdisplay.min.js"></script>'


def page(title, body, scripts=''):
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f'<style>{STYLE}</style>{scripts}</head><body><nav><a href="index.html">Мастерская</a>'
            f'<a href="artists.html">Художники</a><a href="works.html">Работы</a><a href="critics.html">Критики</a>'
            f'<a href="schools.html">Школы</a><a href="timeline.html">Хронология</a>'
            f'</nav>{body}</body></html>')


def esc(text):
    return html.escape(plain(text or ''))


NOTE = {'dream': 'сон', 'illumination': 'озарение', 'preparation': 'подготовка', 'incubation': 'вынашивание',
        'set_aside': 'отложенный замысел', 'school_unborn': 'нерождённая школа', 'school_birth': 'рождение школы',
        'influence': 'встреча', 'draft_decision': 'решение о черновике', 'verification': 'проверка',
        'period': 'новый период', 'life_words': 'слова для жизнеописания'}


def marked(text):
    """A draft with its variants visible: {a|b} shown as alternatives."""
    import re
    return re.sub(r'\{([^{}]*)\}', lambda m: '<span class="variants">[' + ' | '.join(
        html.escape(o) for o in m.group(1).split('|')) + ']</span>', html.escape(text or '').replace('&#x27;', "'"))


def notebook_html(record):
    parts = []
    st = record.get('statement') or {}
    if st:
        parts.append(f'<h3>Замысел</h3><p>{esc(st.get("idea"))}</p><p class="muted">{esc(st.get("thought"))}</p>')
    for h in record.get('interrogation') or []:
        iv = h['interrogation']
        parts.append(f'<p><b>Внутренний критик, раунд {h["round"] + 1}: {html.escape(iv["verdict"])}</b><br>'
                     f'{esc(iv.get("reasons") or "")}</p>')
    for d in record.get('drafts') or []:
        parts.append(f'<h3>Черновик {html.escape(d["id"])}</h3><pre>{marked(d.get("text"))}</pre>'
                     f'<p class="muted">Дневник: {esc(d.get("diary"))}</p>'
                     + (f'<p class="muted">Форма: {html.escape("; ".join(d["form_problems"]))}</p>' if d.get('form_problems') else '')
                     + (f'<p class="muted">Чтение: {html.escape(d["reading"]["verdict"])} — {esc(d["reading"]["reasons"])}</p>'
                        if d.get('reading') else ''))
    for e in record.get('entries') or []:
        if isinstance(e.get('result'), dict) and e['result'].get('diary'):
            parts.append(f'<p class="muted">{html.escape(e["step"])}: {marked(e["result"]["diary"])}</p>')
    if record.get('apparatus'):
        parts.append('<p class="muted">Аппарат разночтений сохранён: варианты, из которых выбран итоговый текст.</p>')
    return ''.join(parts)


def site(at, out: Path):
    from shutil import copyfile
    out.mkdir(parents=True, exist_ok=True)
    (out/'scores').mkdir(exist_ok=True)
    life = at.life
    rows = ''.join(f'<tr><td><a href="artist-{a.id}.html">{esc(at.name(a))}</a></td><td>{ART.get(a.art, a.art)}</td>'
                   f'<td>{LANGUAGE_NAMES.get(a.language, a.language)}</td><td>{a.status}</td><td>{len(a.catalogue)}</td>'
                   f'<td>{esc(a.school)}</td></tr>' for a in life.artists)
    (out/'artists.html').write_text(page('Художники', '<h1>Художники</h1><table><tr><th>Имя</th><th>Искусство</th>'
                                         '<th>Язык</th><th>Статус</th><th>Работ</th><th>Школа</th></tr>' + rows + '</table>'))
    live = [(a, w) for a, w in at.works() if not w.get('synthetic') or at.files(w['id'])]
    rows = ''.join(f'<tr><td><a href="work-{w["id"]}.html">{w["id"]}</a></td><td>{esc(at.name(a))}</td>'
                   f'<td>{ART.get(a.art, a.art)}</td><td>{w["night"]}</td><td>{w["verdict"]}</td>'
                   f'<td>{esc(w.get("school") or "")}</td></tr>' for a, w in live)
    (out/'works.html').write_text(page('Работы', '<h1>Работы</h1><table><tr><th>Работа</th><th>Автор</th><th>Искусство</th>'
                                       '<th>Ночь</th><th>Вердикт</th><th>Школа</th></tr>' + rows + '</table>'))
    for a in life.artists:
        works = ''.join(f'<li><a href="work-{w["id"]}.html">{w["id"]}</a> — ночь {w["night"]}, {w["verdict"]}'
                        f'{": " + esc(w.get("idea"))[:120] if w.get("idea") else ""}</li>'
                        for w in a.catalogue if (a, w) in live)
        chapters = ''.join(f'<h3 class="muted">ночь {c["night"]} · {c["kind"]}</h3><p>{esc(c["text"])}</p>'
                           for c in life.biographies[a.id].chapters if c.get('text'))
        notes = ''.join(f'<li>ночь {n["night"]} · {NOTE.get(n["kind"], n["kind"])}'
                        + (f': {esc(n.get("idea") or n.get("image") or n.get("name") or "")[:200]}'
                           if (n.get("idea") or n.get("image") or n.get("name")) else '') + '</li>'
                        for n in a.notebook if n['kind'] not in ('draft_decision', 'verification', 'incubation'))
        body = (f'<h1>{esc(at.name(a))}</h1><p class="muted">{ART.get(a.art, a.art)} · '
                f'{LANGUAGE_NAMES.get(a.language, a.language)} · родился {a.birth[:10]} · {a.status} · школа {esc(a.school)}'
                f'{" · учителя: " + ", ".join(a.teachers) if a.teachers else ""}</p><p>{esc(a.portrait)}</p>'
                f'<h2>Работы</h2><ul>{works or "<li class=muted>пока синтетические</li>"}</ul>'
                f'<h2>Жизнеописание</h2>{chapters or "<p class=muted>главы ещё не написаны</p>"}'
                f'<h2>Блокнот</h2><ul class="muted">{notes or "<li>пусто</li>"}</ul>')
        (out/f'artist-{a.id}.html').write_text(page(at.name(a), body))
    for a, w in live:
        parts, scripts = [], ''
        original, ru = at.text(w['id'])
        if original:
            parts.append(f'<h2>Текст</h2><pre>{html.escape(original)}</pre>')
        if ru:
            parts.append(f'<h2>Перевод</h2><pre>{html.escape(ru)}</pre>')
        scores = [p for p in at.files(w['id']) if p.suffix == '.musicxml']
        if scores:
            score = scores[-1]
            copyfile(score, out/'scores'/f'{w["id"]}.musicxml')
            midi = out/'scores'/f'{w["id"]}.mid'
            try:
                from music21 import converter
                converter.parse(score).write('midi', fp=midi)
                parts.append(f'<h2>Сыграть по нотам</h2><midi-player src="scores/{midi.name}" '
                             f'sound-font></midi-player>')
                scripts += PLAYER
            except Exception as exc:
                parts.append(f'<p class="muted">MIDI не собран: {html.escape(str(exc))}</p>')
            parts.append(f'<h2>Партитура</h2><div id="score"></div><script>new opensheetmusicdisplay.'
                         f'OpenSheetMusicDisplay("score").load("scores/{w["id"]}.musicxml").then(o=>o.render())</script>')
            scripts += NOTATION
        record = at.notebook(w['id'])
        if record:
            parts.append('<h2>Блокнот работы</h2>' + notebook_html(record))
        reviews = ''.join(f'<p><b><a href="critic-{html.escape(r["critic"])}.html">{html.escape(r["lens"]["name"])}</a></b> <span class="muted">ночь {r["night"]}, '
                          f'оценка {r["score"]:.2f}</span><br>{esc(r.get("text"))}</p>' for r in at.reviews(w['id']))
        sources = ''.join(f'<li>{html.escape(str(p.relative_to(at.root)))}</li>' for p in at.files(w['id']))
        body = (f'<h1>{w["id"]}</h1><p class="muted"><a href="artist-{a.id}.html">{esc(at.name(a))}</a> · '
                f'{ART.get(a.art, a.art)} · ночь {w["night"]} · {w["verdict"]} · {esc(w.get("school") or "")}</p>'
                + (f'<p>{esc(w.get("idea"))}</p>' if w.get('idea') else '') + ''.join(parts)
                + (f'<h2>Рецензии</h2>{reviews}' if reviews else '')
                + f'<h2>Первоисточники</h2><ul class="muted">{sources or "<li>нет файлов</li>"}</ul>')
        (out/f'work-{w["id"]}.html').write_text(page(w['id'], body, scripts))
    critics = {}
    for r in life.reception.reviews:
        critics.setdefault(r['critic'], []).append(r)
    rows = ''.join(f'<tr><td><a href="critic-{html.escape(c)}.html">{html.escape(rs[0]["lens"]["name"])}</a></td>'
                   f'<td>{len(rs)}</td><td>{sum(r["score"] for r in rs) / len(rs):.2f}</td></tr>' for c, rs in critics.items())
    (out/'critics.html').write_text(page('Критики', '<h1>Критики</h1><table><tr><th>Критик</th><th>Рецензий</th>'
                                         '<th>Средняя оценка</th></tr>' + rows + '</table>'))
    for c, rs in critics.items():
        lens = rs[0]['lens']
        body = (f'<h1>{html.escape(lens["name"])}</h1><p class="muted">{html.escape(str(lens.get("voice", "")))} · '
                f'репутация {lens["reputation"]:.2f}</p>' + ''.join(
                    f'<div class="work"><a href="work-{r["work"]}.html">{r["work"]}</a> <span class="muted">ночь {r["night"]}, '
                    f'оценка {r["score"]:.2f}{", пересмотр" if r.get("revision_of") else ""}</span><p>{esc(r.get("text"))}</p></div>'
                    for r in rs))
        (out/f'critic-{c}.html').write_text(page(lens['name'], body))
    from .music.schools import SCHOOLS as MUSIC
    from .writing.schools import SCHOOLS as LETTERS
    used = {}
    for a, w in at.works():
        used.setdefault(w.get('school'), set()).add(a.id)
    rows = ''.join(f'<tr><td>{html.escape(k)}</td><td>музыка</td><td>{len(used.get(k, ()))}</td><td class="muted">'
                   f'{html.escape((MUSIC[k].__doc__ or "").strip().splitlines()[0] if MUSIC[k].__doc__ else "")}</td></tr>'
                   for k in sorted(MUSIC))
    rows += ''.join(f'<tr><td>{html.escape(k)}</td><td>литература</td><td>{len(used.get(k, ()))}</td>'
                    f'<td class="muted">{html.escape(LETTERS[k].RULES)}</td></tr>' for k in sorted(LETTERS))
    born = ''.join(f'<div class="work"><h2>{html.escape(r["name"])}</h2><p class="muted">основал '
                   f'{html.escape(r.get("author", ""))}, ночь {r.get("night")}</p><ul>' + ''.join(
                       f'<li>{html.escape(m)}</li>' for m in r.get('manifesto', {}).get('manifesto', []))
                   + f'</ul><pre class="muted">{html.escape(r.get("source", ""))}</pre></div>' for r in life.schools.values())
    (out/'schools.html').write_text(page('Школы', '<h1>Школы</h1><table><tr><th>Школа</th><th>Искусство</th>'
                                         '<th>Художников</th><th>Правила</th></tr>' + rows + '</table>'
                                         + (f'<h1>Рождённые в мастерской</h1>{born}' if born else '')))
    names = {a.id: at.name(a) for a in life.artists}
    rows = ''.join(f'<tr><td>{e["date"][:10]}</td><td>{e["night"]}</td><td><a href="artist-{e["artist"]}.html">'
                   f'{esc(names.get(e["artist"], e["artist"]))}</a></td><td>{e["kind"]}</td></tr>' for e in life.events)
    (out/'timeline.html').write_text(page('Хронология', '<h1>Хронология</h1><table>' + rows + '</table>'))
    working = ', '.join(f'<a href="artist-{a.id}.html">{esc(at.name(a))}</a>' for a in life.working())
    body = (f'<h1>Мастерская {html.escape(life.cluster)}</h1><p class="muted">ночь {life.night} · {life.date()[:10]}</p>'
            f'<p>Работают: {working}</p><p>Художников за всю историю: {len(life.artists)}, работ: '
            f'{sum(len(a.catalogue) for a in life.artists)}, живых работ: {len(live)}, рецензий: '
            f'{len(life.reception.reviews)}, событий: {len(life.events)}.</p>')
    (out/'index.html').write_text(page(f'Мастерская {life.cluster}', body))
    return out


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='mnemo view')
    ap.add_argument('--root', type=Path, required=True, help='atelier directory with lineage.json and nights/')
    ap.add_argument('what', choices=['artists', 'artist', 'work', 'lives', 'night', 'timeline', 'site'])
    ap.add_argument('id', nargs='?')
    ap.add_argument('--out', type=Path)
    a = ap.parse_args(argv)
    at = Atelier(a.root)
    if a.what == 'site':
        print(site(at, a.out or a.root/'site'))
    else:
        {'artists': lambda: show_artists(at), 'timeline': lambda: show_timeline(at),
         'artist': lambda: show_artist(at, a.id), 'work': lambda: show_work(at, a.id),
         'lives': lambda: show_lives(at, a.id), 'night': lambda: show_night(at, int(a.id))}[a.what]()
