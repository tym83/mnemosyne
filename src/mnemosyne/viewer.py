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
from .writing import poetics
from .writing.memory import composer, hearings

ART = {'music': 'музыка', 'literature': 'литература'}
LANG_RU = {'ru': 'русский', 'en': 'английский', 'fr': 'французский', 'es': 'испанский', 'pt': 'португальский',
           'de': 'немецкий', 'it': 'итальянский', 'pl': 'польский', 'sr': 'сербский', 'el': 'греческий',
           'ja': 'японский', 'zh': 'китайский', 'fa': 'персидский', 'ar': 'арабский', 'hi': 'хинди',
           'yo': 'йоруба', 'la': 'латынь', 'sa': 'санскрит'}


class Atelier:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.life = Lineage.restore(json.loads((self.root/'lineage.json').read_text()))
        # A lived history keeps nights under nights/; a studio volume keeps them beside lineage.json.
        self.home = self.root/'nights' if (self.root/'nights').is_dir() else self.root
        # A continuous life keeps each creator's sessions under creators/<id>/<stamp>.
        self.nights = sorted(p for p in self.home.iterdir() if p.is_dir() and p.name not in ('ledger', 'cache', 'site')
                             and ((p/'decode.json').exists() or (p/'request.json').exists() or p.name.isdigit()
                                  or p.name == 'creators'))
        self.year = [json.loads(l) for l in (self.root/'year.jsonl').read_text().splitlines()] \
            if (self.root/'year.jsonl').exists() else []
        from .writing.memory import Memory
        self.memory = Memory(self.root)
        from . import lexicon
        self.lexicon = lexicon.load(self.root)

    def ru(self, text):
        """The Russian of a text: itself when it is Russian, the Translator's rendering, or None."""
        from .writing.memory import foreign
        if not text or not foreign(text):
            return text
        return self.memory.get(text)

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
            # A composer's notebook is also kept in the work: it outlasts the files of the session.
            for _, w in self.works():
                record = (w.get('process') or {}).get('composer')
                if isinstance(record, dict) and record.get('opus'):
                    self._notebooks.setdefault(record['opus'], record)
        return self._notebooks.get(wid)

    def records(self):
        """Every night's notebook, finished or not: rejected ideas and requested schools included."""
        self.notebook('')
        return list(self._notebooks.values())

    def text(self, wid):
        texts = [p for p in self.files(wid) if p.suffix == '.txt' and not p.name.endswith('.ru.txt')]
        ru = [p for p in self.files(wid) if p.name.endswith('.ru.txt')]
        original = texts[0].read_text() if texts else None
        # The Translator's later rendering wins over the one made on the night.
        later = self.memory.get(original) if original else None
        return original, later or (ru[0].read_text() if ru else None)

    def reviews(self, wid):
        return [r for r in self.life.reception.reviews if r['work'] == wid]


def show_artists(at):
    for a in at.life.artists:
        print(f'{a.id:14} {at.name(a)[:28]:28} {ART.get(a.art, a.art):10} {a.language:3} {a.status:8} '
              f'works {len(a.catalogue):3}  school {a.school}')


def show_artist(at, aid):
    a = at.artist(aid)
    print(f'{at.name(a)} ({a.id}) — {ART.get(a.art, a.art)}, язык: {LANG_RU.get(a.language, a.language)}')
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
.tr .ru{display:none}body.ru .tr .ru{display:revert}body.ru .tr .orig{display:none}
.toc{font:14px system-ui,sans-serif;border:1px solid var(--line);border-radius:6px;padding:10px 14px;margin:0 0 20px}
.toc ol{list-style:none;padding:0;margin:6px 0 10px}.toc li{margin:3px 0}.toc li.l2{padding-left:14px}
.toc a{text-decoration:none}.toc #trall{float:none;position:static;width:100%}
@media (min-width:1240px){.toc{position:fixed;top:24px;left:calc(50% + 450px);width:220px;max-height:calc(100vh - 48px);overflow:auto;margin:0}}
:target{scroll-margin-top:16px}h1.title{margin-bottom:4px}.byline{font-size:1.1em;margin-top:0}
#trall{position:sticky;top:8px;float:right;z-index:2;font:14px system-ui,sans-serif;color:var(--bg);background:var(--accent);border:0;border-radius:6px;padding:6px 12px;cursor:pointer}
details{margin:8px 0}summary{cursor:pointer;color:var(--muted);font:14px system-ui,sans-serif}
dl dt{color:var(--muted);font:14px system-ui,sans-serif;margin-top:12px}dl dd{margin:2px 0 0}
.cmd{font:14px ui-monospace,Menlo,monospace;background:var(--line);padding:8px 10px;border-radius:4px}
.lead{font-size:1.05em;border-left:3px solid var(--accent);padding-left:14px}
#score{background:#fff;border-radius:6px;padding:8px;overflow-x:auto}
"""
PLAYER = ('<script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,'
          'npm/focus-visible@5.2.0,npm/html-midi-player@1.5.0"></script>')
NOTATION = '<script src="https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.8.0/build/opensheetmusicdisplay.min.js"></script>'


FLIP = '''<script>
function flipAll(){const on=document.body.classList.toggle('ru');
document.getElementById('trall').textContent=on?'Оригинал':'Перевод на русский';try{localStorage.setItem('ru',on?'1':'')}catch(e){}}
try{if(localStorage.getItem('ru'))flipAll()}catch(e){}
if(!document.querySelector('.tr'))document.getElementById('trall').remove()
</script>'''


def page(title, body, scripts='', toc=None):
    """A page; with toc, a contents list that rides along on the right and holds the translation switch."""
    button = '<button id="trall" onclick="flipAll()">Перевод на русский</button>'
    aside = ''
    if toc:
        aside = ('<aside class="toc"><b>Содержание</b><ol>' + ''.join(
            f'<li class="l{level}"><a href="#{anchor}">{label}</a></li>' for anchor, label, level in toc)
            + f'</ol>{button}</aside>')
        button = ''
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f'<style>{STYLE}</style>{scripts}</head><body><nav><a href="index.html">Мастерская</a>'
            f'<a href="artists.html">Творцы</a><a href="works.html">Работы</a><a href="critics.html">Критики</a>'
            f'<a href="schools.html">Школы</a><a href="lexicon.html">Словарь</a><a href="timeline.html">Хронология</a><a href="restore.html">Восстановление</a>'
            f'</nav>{button}{aside}{body}{FLIP}</body></html>')


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


GENRE_RU = {'work': 'рецензия', 'creator': 'статья о творце', 'period': 'статья о периоде', 'obituary': 'некролог',
            'manifesto': 'разбор манифеста', 'school': 'обзор школы'}

CHAPTER = {'birth': 'рождение', 'first_accepted': 'первая принятая работа', 'writer_work': 'работа',
           'death': 'смерть', 'despair': 'отчаяние', 'illness': 'болезнь', 'school_birth': 'рождение школы',
           'teacher': 'ученичество', 'renounce': 'уход из искусства'}

STATUS = {'accepted': 'работа принята', 'unfinished': 'работа не доведена', 'idea_rejected': 'замысел отвергнут критиком',
          'school_requested': 'заявлена новая школа', 'searching': 'ночь не закончена', 'failed': 'ночь сорвалась'}

VERDICT = {'accept': 'принята', 'rewrite': 'не доведена', 'repetition': 'повтор', 'unfinished': 'не доведена'}

STATEMENT = (('idea', 'Замысел'), ('superobjective', 'Сверхзадача'), ('message', 'Мысль'), ('thought', 'Мысль'),
             ('why_i_must_say_it', 'Почему я должен это сказать'), ('why_now', 'Почему сейчас'),
             ('freshness', 'В чём новизна'), ('not_a_cliche_because', 'Почему это не штамп'),
             ('emotions', 'Чувства'), ('how_it_changes_a_heart', 'Что это меняет в читателе'),
             ('why_admired', 'За что этим можно восхищаться'), ('timeless_or_of_the_world', 'Вечное или сегодняшнее'),
             ('risks', 'Чего я боюсь'), ('operators_used', 'Приёмы и учителя'))

SCHOOL_RU = {
    'haiku': ('Хайку', 'Японское трёхстишие 5–7–5: одно мгновение, сезонное слово, разрыв между образами.'),
    'chastushka': ('Частушка', 'Русский фольклорный куплет: четыре строки, хорей, рифма, поворот в последней строке.'),
    'sonnet': ('Сонет', 'Четырнадцать строк с рифмовкой; мысль поворачивает в последних строках.'),
    'bylina': ('Былина', 'Эпический сказ тоническим стихом: зачин, повторы, постоянные эпитеты.'),
    'fairy_tale': ('Волшебная сказка', 'Сказка по функциям Проппа: недостача, путь, испытание, возвращение.'),
    'eluard': ('Элюар', 'Сюрреалистическая лирика Поля Элюара: свободный стих, рефрен, сцепление несоединимых образов.'),
    'pavic': ('Павич', 'Роман-словарь в духе «Хазарского словаря»: статьи с перекрёстными ссылками, читать можно в любом порядке.'),
    'minimalism': ('Минимализм', 'Короткая проза в духе Карвера: сцены без авторских оценок и объяснённых чувств, главное — в недосказанном.'),
    'psychological_realism': ('Психологический реализм', 'Проза в духе Толстого, Флобера и позднего Чехова: внутренняя жизнь рассказана, мотивы прослежены, время течёт и меняет героя.'),
    'polyphony': ('Полифония', 'Роман голосов в духе Достоевского по Бахтину: равноправные сознания, сцена-скандал, диалог как событие.'),
    'magical_realism': ('Магический реализм', 'Семейная хроника в духе Маркеса: чудо рассказано как бытовой факт, точная гипербола, возвращающиеся имена.'),
    'stream_of_consciousness': ('Поток сознания', 'Проза в духе Вулф: один день во внутреннем времени, длинные фразы, скользящий фокус.'),
    'skaz': ('Сказ', 'Рассказ от лица носителя особой речи в духе Лескова и Зощенко: слово рассказчика и есть форма.'),
    'platonov': ('Платонов', 'Смысловой сдвиг в языке и странствие искателя истины по недостроенному миру.'),
    'faulkner': ('Фолкнер', 'Одно событие, рассказанное несколькими голосами; каждая глава подписана именем говорящего.'),
    'epistolary': ('Эпистолярный роман', 'История, рассказанная только письмами: сюжет движется между письмами, а не внутри них.'),
    'nouveau_roman': ('Новый роман', 'Проза вещей и поверхностей в духе Роб-Грийе: одна сцена описана снова и снова со сдвигами.'),
    'gothic': ('Готика', 'Рассказ ужаса: дом, тайна, возвращающееся прошлое; страх нарастает по ступеням.'),
    'tintinnabuli': ('Тинтиннабули', 'Метод Арво Пярта: мелодия по ступеням и голос, звучащий по трезвучию.'),
    'stochastic': ('Стохастическая', 'Музыка масс звуков Ксенакиса: плотности и распределения вместо мелодий.'),
    'micropolyphony': ('Микрополифония', 'Густые каноны Лигети, в которых отдельные голоса сливаются в ткань.'),
    'serial': ('Серийная', 'Двенадцатитоновая серия и её преобразования.'),
    'feldman': ('Фелдман', 'Тихие, очень долгие формы Мортона Фелдмана, почти без событий.'),
    'process': ('Процессуальная', 'Музыка постепенного процесса: фазовые сдвиги и медленные изменения.'),
    'additive': ('Аддитивная', 'Мотив растёт и убывает по одной ноте за раз.'),
    'in_c': ('«In C»', 'Открытая форма Терри Райли: исполнители идут по общим фигурам каждый в своём темпе.'),
    'spectral': ('Спектральная', 'Гармония из спектра обертонов одного звука.'),
    'sonorism': ('Сонористика', 'Польская сонористика: кластеры и тембровые пятна вместо нот.'),
    'messiaen': ('Мессиан', 'Лады ограниченной транспозиции и необратимые ритмы.'),
    'ustvolskaya': ('Уствольская', 'Жёсткие кластеры, удары и аскетичная сила.'),
    'chance': ('Музыка случая', 'Решения принимает жребий, как у Кейджа.'),
    'tempo_canon': ('Темповый канон', 'Канон, в котором голоса идут в разных темпах, как у Нанкарроу.'),
    'aleatoric_counterpoint': ('Алеаторический контрапункт', 'Голоса заданы, но их встречи свободны, как у Лютославского.'),
    'fibonacci': ('Фибоначчи', 'Пропорции формы по числам Фибоначчи.'),
    'polystylism': ('Полистилистика', 'Столкновение стилей и цитат, как у Шнитке.'),
    'scelsi': ('Шелси', 'Музыка одного звука, раскрытого изнутри.'),
    'drone': ('Дроун', 'Долгий выдержанный тон, на котором всё меняется медленно.'),
    'gregorian': ('Григорианский хорал', 'Одноголосное литургическое пение в восьми церковных ладах: речитация, невмы и мелизмы.'),
    'ancient_greek': ('Древнегреческая монодия', 'Песня по тетрахордам трёх родов, ритм стиха и гетерофония лиры и авлоса.'),
    'organum': ('Органум', 'Многоголосие школы Нотр-Дам: долгий тенор хорала и верхние голоса в ритмических модусах.'),
    'ars_nova': ('Ars nova', 'Изоритмический мотет: талея и колор в теноре, гокет, каденции с двумя вводными тонами.'),
    'classical': ('Венский классицизм', 'Периоды из вопроса и ответа над ясной гармонией: каденции, альбертиев бас, путь в доминанту и обратно.'),
    'romantic': ('Романтическая лирика', 'Поющая мелодия над широкими арпеджио, хроматическая гармония и волны динамики к одной вершине.'),
    'renaissance_polyphony': ('Полифония строгого стиля', 'Точки имитации, плавные голоса, диссонанс только проходящий или задержанный, каденции на финалисе.'),
    'fugue': ('Фуга', 'Тема, ответ на квинте и противосложение; интермедии из обрывков темы, стретта, органный пункт.'),
    'basso_continuo': ('Генерал-бас', 'Бас на каждую долю с аккордами над ним, ритурнель и секвенции по квинтовому кругу, террасная динамика.'),
}

FILE_KIND = (
    ('woven/', '.musicxml', 'Партитура-носитель: в оттенках динамики нот зашифрован кусок резервной копии кластера.'),
    ('woven/', '.catalogue.json', 'Каталог носителя: какие куски копии лежат в этой работе и в каком порядке.'),
    ('woven/', '.variants.json', 'Том разночтений: выбор между авторскими вариантами слов шифрует кусок копии.'),
    ('woven/', '.audience.json', 'Отклик публики: тоже носитель куска копии.'),
    ('', 'draft.musicxml', 'Черновик партитуры, каким его оставил композитор.'),
    ('', 'notebook.json', 'Блокнот ночи: замысел, внутренний критик, выбор школы, все черновики и чтения.'),
    ('', '.ru.txt', 'Перевод текста на русский, сделанный Переводчиком.'),
    ('', '.txt', 'Текст работы на языке автора.'),
    ('', '.mid', 'MIDI, собранный из нот.'),
)


def file_kind(path):
    name = str(path)
    for where, suffix, text in FILE_KIND:
        if where in name and name.endswith(suffix):
            return text, bool(where)
    return '', False


def school_name(k):
    if not k:
        return ''
    return SCHOOL_RU[k][0] if k in SCHOOL_RU else (poetics.load(k) or {}).get('name', k)


def school_link(k):
    return f'<a href="school-{html.escape(k)}.html">{html.escape(school_name(k))}</a>' if k else ''


def toggle(original_html, russian_html, block=True):
    """The original in place; the translation replaces it on demand."""
    if block:
        return (f'<div class="tr"><div class="orig">{original_html}</div><div class="ru">{russian_html}</div>'
                f'</div>')
    return f'<span class="tr"><span class="orig">{original_html}</span><span class="ru">{russian_html}</span></span>'


def ru_block(at, text, tag='p'):
    if not text:
        return ''
    russian = at.ru(text)
    if russian is text:
        return f'<{tag}>{esc(text)}</{tag}>'
    if russian:
        return toggle(f'<{tag}>{esc(text)}</{tag}>', f'<{tag}>{esc(russian)}</{tag}>')
    return f'<{tag}>{esc(text)}</{tag}>'


def ru_inline(at, text):
    russian = at.ru(text)
    if russian is text or not russian:
        return esc(text)
    return toggle(esc(text), esc(russian), block=False)


def ru_short(at, text, n=200):
    """A shortened text with its shortened translation: cut before markup, never through it."""
    if not text:
        return ''
    cut = lambda t: plain(t)[:n] + ('…' if len(plain(t)) > n else '')
    russian = at.ru(text)
    if russian is text or not russian:
        return html.escape(cut(text))
    return toggle(html.escape(cut(text)), html.escape(cut(russian)), block=False)


def statement_html(at, st):
    rows = []
    for k, label in STATEMENT[1:]:
        value = st.get(k)
        if not value:
            continue
        items = value if isinstance(value, list) else [value]
        rows.append(f'<dt>{label}</dt><dd>' + ''.join(ru_block(at, v) for v in items) + '</dd>')
    return '<dl>' + ''.join(rows) + '</dl>'


def notebook_html(at, record):
    parts = []
    st = record.get('statement') or {}
    if st:
        parts.append('<h3 id="manifesto">Манифест замысла</h3><p class="muted">Прежде чем писать, творец отвечает себе, '
                     'что и зачем он делает.</p>' + statement_html(at, st))
    rounds = record.get('interrogation') or []
    if rounds:
        parts.append('<h3 id="critic">Допрос внутреннего критика</h3><p class="muted">Критик читает замысел и решает: принять '
                     'или переписать. Замысел переписывается, пока критик не примет его или не кончатся раунды.</p>')
    for h in rounds:
        iv = h['interrogation']
        lists = ''.join(f'<dt>{label}</dt><dd><ul>' + ''.join(f'<li>{ru_inline(at, x)}</li>' for x in iv[k]) + '</ul></dd>'
                        for k, label in (('questions_back', 'Вопросы автору'), ('weak_answers', 'Слабые ответы'),
                                         ('cliches_found', 'Найденные штампы')) if iv.get(k))
        parts.append(f'<div class="work"><h4>Раунд {h["round"] + 1} · {VERDICT.get(iv["verdict"], iv["verdict"])}</h4>'
                     + (f'<dl><dt>Замысел в этом раунде</dt><dd>{ru_block(at, (h.get("statement") or {}).get("idea"))}</dd>'
                        if (h.get('statement') or {}).get('idea') else '<dl>')
                     + f'<dt>Вывод</dt><dd>{ru_block(at, iv.get("reasons"))}</dd>'
                     + (f'<dt>Что сохранить</dt><dd>{ru_block(at, iv.get("keep"))}</dd>' if iv.get('keep') else '')
                     + lists + '</dl></div>')
    method = record.get('method')
    music = composer(record)
    if method:
        parts.append('<h3 id="method">Выбор школы: ' + (school_link(method['school']) if method.get('kind') == 'school'
                                             else 'новая школа «' + esc(method['school']) + '»') + '</h3>'
                     + ru_block(at, method.get('reason')))
        if music:
            parts.append('<dl>' + ''.join(f'<dt>{label}</dt><dd>{ru_block(at, method[k])}</dd>'
                                          for k, label in (('concept', 'Замысел формы'), ('principle', 'Принцип'),
                                                           ('transformation', 'Преображение'))
                                          if method.get(k)) + '</dl>')
    shades = record.get('halftones') if music else None
    if shades:
        rows = [(f'Мысль: {esc(shades["thought"].get("shade"))}', shades['thought']),
                (f'Рука: {esc(shades["embodiment"].get("shade"))}', shades['embodiment'])] \
            if isinstance(shades.get('thought'), dict) and isinstance(shades.get('embodiment'), dict) else []
        rows += [(f'{esc(n.get("emotion"))}: {esc(n.get("shade"))}', n) for n in shades.get('nuances') or []]
        parts.append('<h3 id="halftones">Полутона</h3><p class="muted">Какой оттенок у каждого чувства — так, '
                     'как его даёт только этот композитор.</p>' + ru_block(at, shades.get('overall')) + '<dl>'
                     + ''.join(f'<dt>{head}</dt><dd>{ru_block(at, v.get("why_mine"))}{ru_block(at, v.get("how_it_shows"))}</dd>'
                               for head, v in rows) + '</dl>')
    heard = hearings(record) if music else []
    if heard:
        parts.append('<h3 id="hearings">Как композитор слушал свои черновики</h3><p class="muted">После каждого эскиза '
                     'и черновика композитор читает партитуру и анализ и решает: принять или переписать.</p>')
    for n, h in enumerate(heard, 1):
        what = 'Эскиз' if h['step'] == 'listen:sketch' else f'Черновик {h["step"].rsplit(":", 1)[-1]}'
        parts.append(f'<div class="work"><h4 id="hearing-{n}">{what} · {VERDICT.get(h.get("verdict"), h.get("verdict") or "")}'
                     + (f' · {h["quality"]:.2f}' if isinstance(h.get('quality'), (int, float)) else '') + '</h4>'
                     + ru_block(at, h.get('reasons'))
                     + ('<ul>' + ''.join(f'<li>{ru_inline(at, c)}</li>' for c in h.get('corrections') or []) + '</ul>'
                        if h.get('corrections') else '') + '</div>')
    birth = record.get('school_birth') or {}
    for n, h in enumerate(birth.get('attempts') or [], 1):
        p, j = h['poetics'], h['judgement']
        parts.append(f'<div class="work"><h3 id="founding-{n}">Основание школы, попытка {n}: '
                     f'«{ru_inline(at, p.get("name"))}»</h3><ol>' + ''.join(f'<li>{ru_inline(at, m)}</li>'
                                                                         for m in p.get('manifesto', []))
                     + f'</ol><dl><dt>Картина мира</dt><dd>{ru_block(at, p.get("worldview"))}</dd>'
                     f'<dt>Против чего</dt><dd>{ru_block(at, p.get("against"))}</dd>'
                     f'<dt>Внутренний критик: {VERDICT.get(j.get("verdict"), j.get("verdict"))}</dt>'
                     f'<dd>{ru_block(at, j.get("reasons"))}'
                     + (f'<p>Похоже на: {ru_inline(at, j["renaming_of"])}</p>' if j.get('renaming_of') else '')
                     + '</dd></dl></div>')
    for n, d in enumerate(record.get('drafts') or [], 1):
        reading = d.get('reading') or {}
        parts.append(f'<h3 id="draft-{n}">Черновик {n}: {ru_inline(at, d.get("title"))}</h3>'
                     f'<details><summary>текст черновика с вариантами</summary><pre>{marked(d.get("text"))}</pre></details>'
                     + ('<p class="muted">Дневник автора:</p>' + ru_block(at, d.get('diary')) if d.get('diary') else '')
                     + (f'<p class="muted">Форма не удержана: {html.escape("; ".join(d["form_problems"]))}</p>'
                        if d.get('form_problems') else '')
                     + (f'<p class="muted">Автор перечитал: {VERDICT.get(reading["verdict"], reading["verdict"])}</p>'
                        + ru_block(at, reading.get('reasons')) if reading else ''))
    let_go = record.get('let_go')
    if let_go:
        why = ('наперекор и критику, и собственному вкусу: уверенность в себе перевесила'
               if let_go.get('against_taste') else 'вещь выше порога его вкуса')
        parts.append(f'<h3 id="let-go">Отпустил</h3><p>Внутренний критик просил ещё правок, но автор отдал вещь: '
                     f'{why} (оценка {let_go["quality"]:.2f}, порог вкуса {let_go["threshold"]:.2f}'
                     + (f', уверенность {let_go["assurance"]:+.2f}' if 'assurance' in let_go else '')
                     + '). Несделанное:</p><ul>' + ''.join(f'<li>{ru_inline(at, c)}</li>' for c in let_go['left_undone'])
                     + '</ul>')
    if record.get('apparatus'):
        parts.append('<p class="muted">Аппарат разночтений сохранён: варианты, из которых выбран итоговый текст.</p>')
    return ''.join(parts)


def site(at, out: Path):
    from shutil import copyfile
    out.mkdir(parents=True, exist_ok=True)
    (out/'scores').mkdir(exist_ok=True)
    life = at.life
    rows = ''.join(f'<tr><td><a href="artist-{a.id}.html">{esc(at.name(a))}</a></td><td>{ART.get(a.art, a.art)}</td>'
                   f'<td>{LANG_RU.get(a.language, a.language)}</td><td>{a.status}</td><td>{len(a.catalogue)}</td>'
                   f'<td>{school_link(a.school) if a.school in SCHOOL_RU else esc(a.school or "")}</td></tr>' for a in life.artists)
    (out/'artists.html').write_text(page('Творцы', '<h1>Творцы</h1><table><tr><th>Имя</th><th>Искусство</th>'
                                         '<th>Язык</th><th>Статус</th><th>Работ</th><th>Школа</th></tr>' + rows + '</table>'))
    live = [(a, w) for a, w in at.works() if not w.get('synthetic') or at.files(w['id'])]
    rows = ''.join(f'<tr><td><a href="work-{w["id"]}.html">{w["id"]}</a></td><td>{esc(at.name(a))}</td>'
                   f'<td>{ART.get(a.art, a.art)}</td><td>{w["night"]}</td><td>{VERDICT.get(w["verdict"], w["verdict"])}</td>'
                   f'<td>{school_link(w.get("school"))}</td></tr>' for a, w in live)
    (out/'works.html').write_text(page('Работы', '<h1>Работы</h1><table><tr><th>Работа</th><th>Автор</th><th>Искусство</th>'
                                       '<th>Ночь</th><th>Вердикт</th><th>Школа</th></tr>' + rows + '</table>'))
    done = {w['id'] for _, w in live}
    for r in at.records():
        if r['opus'] in done:
            continue
        a = at.artist(r['artist'])
        idea = (r.get('statement') or {}).get('idea')
        body = (f'<h1>Ночь {r.get("night")}: {STATUS.get(r.get("status"), r.get("status"))}</h1><p class="muted">'
                f'<a href="artist-{a.id}.html">{esc(at.name(a))}</a> · {ART.get(a.art, a.art)} · {r["opus"]}</p>'
                + (f'<h2>Замысел</h2><div class="lead">{ru_block(at, idea)}</div>' if idea else '')
                + (f'<p class="muted">{html.escape(r["error"])}</p>' if r.get('error') else '')
                + '<h2>Как прошла ночь</h2>' + notebook_html(at, r))
        (out/f'night-{r["opus"]}.html').write_text(page(f'Ночь {r.get("night")}', body))
    for a in life.artists:
        works = ''.join(f'<li><a href="work-{w["id"]}.html">{w["id"]}</a> — ночь {w["night"]}, '
                        f'{VERDICT.get(w["verdict"], w["verdict"])}, школа {school_link(w.get("school")) or "—"}'
                        f'{": " + ru_short(at, w.get("idea"), 160) if w.get("idea") else ""}</li>'
                        for w in a.catalogue if (a, w) in live)
        from .chronicle import line
        lives = life.biographies[a.id].chapters
        chapters = '<ol class="chronicle">' + ''.join(
            f'<li>{html.escape(line(life, a, c))}</li>' for c in lives) + '</ol>' if lives else ''
        voice = ''.join(
            ''.join(f'<p class="muted">{c.get("date", "")[:10]} · {label}</p>{ru_block(at, (c.get("words") or {}).get(k))}'
                    for k, label in (('diary', 'дневник'), ('letter', 'письмо'), ('image', 'образ'))
                    if (c.get('words') or {}).get(k))
            for c in lives)
        about = ''.join(f'<div class="work"><b><a href="critic-{html.escape(v["critic"])}.html">{html.escape(v["lens"]["name"])}</a></b> '
                        f'<span class="muted">{GENRE_RU.get(v.get("kind"), "")}, оценка {v["score"]:.2f}</span>'
                        f'{ru_block(at, v.get("text"))}</div>'
                        for v in life.reception.reviews if v.get('artist') == a.id and v.get('kind') in ('creator', 'period', 'obituary'))
        notes = ''.join(f'<li>ночь {n["night"]} · {NOTE.get(n["kind"], n["kind"])}'
                        + (f': {esc((n.get("idea") or n.get("image") or n.get("name") or "")[:200])}'
                           if (n.get("idea") or n.get("image") or n.get("name")) else '') + '</li>'
                        for n in a.notebook if n['kind'] not in ('draft_decision', 'verification', 'incubation'))
        body = (f'<h1>{esc(at.name(a))}</h1><p class="muted">{ART.get(a.art, a.art)} · '
                f'{LANG_RU.get(a.language, a.language)} · родился {a.birth[:10]} · {a.status} · школа {school_link(a.school) if a.school in SCHOOL_RU else "вне школ"}'
                f'{" · учителя: " + ", ".join(a.teachers) if a.teachers else ""}</p>{ru_block(at, a.portrait)}'
                f'<h2>Работы</h2><ul>{works or "<li class=muted>пока синтетические</li>"}</ul>'
                + '<h2>Замыслы и ночи</h2><p class="muted">Все ночи творца, и удачные, и нет.</p><ul>' + ''.join(
                    f'<li>ночь {r.get("night")} · <a href="{"work" if r["opus"] in done else "night"}-{r["opus"]}.html">'
                    f'{STATUS.get(r.get("status"), r.get("status"))}</a>'
                    f'{": " + ru_short(at, (r.get("statement") or {}).get("idea")) if (r.get("statement") or {}).get("idea") else ""}</li>'
                    for r in sorted(at.records(), key=lambda r: r.get('night') or 0) if r.get('artist') == a.id) + '</ul>'
                + f'<h2>Биография</h2><p class="muted">Строгая хроника: что случилось и как в те дни творец '
                  f'принимал мир.</p>{chapters or "<p class=muted>пока пусто</p>"}'
                + (f'<h2>Его собственным голосом</h2>{voice}' if voice else '')
                + (f'<h2>О нём писали</h2>{about}' if about else '')
                + f'<h2>Блокнот</h2><ul class="muted">{notes or "<li>пусто</li>"}</ul>')
        (out/f'artist-{a.id}.html').write_text(page(at.name(a), body))
    (out/'files').mkdir(exist_ok=True)
    for a, w in live:
        parts, scripts = [], ''
        record = at.notebook(w['id']) or {}
        original, ru = at.text(w['id'])
        if original:
            text = toggle(f'<pre>{html.escape(original)}</pre>', f'<pre>{html.escape(ru)}</pre>') if ru \
                else f'<pre>{html.escape(original)}</pre>'
            parts.append(f'<div id="text" class="work">{text}</div>')
        scores = [p for p in at.files(w['id']) if p.suffix == '.musicxml']
        if scores:
            # The composer's clean draft for reading; the woven score carries the backup in its dynamics.
            score = next((p for p in scores if p.name == 'draft.musicxml'), scores[-1])
            copyfile(score, out/'scores'/f'{w["id"]}.musicxml')
            midi = out/'scores'/f'{w["id"]}.mid'
            try:
                from music21 import converter
                converter.parse(score).write('midi', fp=midi)
                parts.append(f'<h2 id="play">Сыграть по нотам</h2><midi-player src="scores/{midi.name}" '
                             f'sound-font></midi-player>')
                scripts += PLAYER
            except Exception as exc:
                parts.append(f'<p class="muted">MIDI не собран: {html.escape(str(exc))}</p>')
            parts.append(f'<h2 id="score-head">Партитура</h2><div id="score">загружается…</div><script>(function(){{'
                         f'const view=new opensheetmusicdisplay.OpenSheetMusicDisplay("score",{{drawTitle:false,drawComposer:false,drawCredits:false}});'
                         f'view.load("scores/{w["id"]}.musicxml").then(()=>{{document.getElementById("score")'
                         f'.firstChild.remove?.();view.render()}}).catch(e=>{{document.getElementById("score")'
                         f'.textContent="Ноты не открылись: "+e}})}})()</script>')
            scripts += NOTATION
        process = ('<h2 id="process">Как работа рождалась</h2>' + notebook_html(at, record)) if record else ''
        reviews = ''.join(f'<p><b><a href="critic-{html.escape(r["critic"])}.html">{html.escape(r["lens"]["name"])}</a></b> <span class="muted">ночь {r["night"]}, '
                          f'оценка {r["score"]:.2f}</span></p>{ru_block(at, r.get("text"))}' for r in at.reviews(w['id']))
        sources = []
        for p in at.files(w['id']):
            rel = p.relative_to(at.root)
            (out/'files'/rel).parent.mkdir(parents=True, exist_ok=True)
            copyfile(p, out/'files'/rel)
            what, carrier = file_kind(rel)
            sources.append(f'<li><a href="files/{html.escape(str(rel))}">{html.escape(p.name)}</a>'
                           f'{" · <b>носитель копии</b>" if carrier else ""}<br><span class="muted">{what}</span></li>')
        final = next((d for d in record.get('drafts', []) if d['id'] == record.get('final')), None)
        title = ru_inline(at, final['title']) if final and final.get('title') else w['id']
        idea = record.get('statement', {}).get('idea') or w.get('idea')
        said = (record.get('statement') or {}).get('superobjective')
        body = (f'<h1 class="title">{title}</h1><p class="byline"><a href="artist-{a.id}.html">{esc(at.name(a))}</a></p>'
                f'<p class="muted">{ART.get(a.art, a.art)} · {LANG_RU.get(a.language, a.language)} · школа '
                f'{school_link(w.get("school")) or "—"} · {VERDICT.get(w["verdict"], w["verdict"])} · '
                f'<span title="номер работы">{w["id"]}</span></p>'
                + ''.join(parts)
                + (f'<h2 id="idea">Замысел</h2>'
                   + (f'<p class="muted">Что автор хочет сказать</p><div class="lead">{ru_block(at, said)}</div>'
                      if said else '')
                   + f'<div class="lead">{ru_block(at, idea)}</div>' if idea else '')
                + process
                + (f'<h2 id="reviews">Рецензии</h2>{reviews}' if reviews else '')
                + '<h2 id="sources">Первоисточники</h2><p class="muted">Файлы, из которых собрана эта страница. Носители '
                  'хранят куски зашифрованной резервной копии кластера; как из них поднять кластер — на странице '
                  '<a href="restore.html">Восстановление</a>.</p>'
                + f'<ul>{"".join(sources) or "<li>нет файлов</li>"}</ul>')
        toc = ([('text', 'Текст', 1)] if original else []) + ([('play', 'Сыграть', 1), ('score-head', 'Партитура', 1)] if scores else []) \
            + ([('idea', 'Замысел', 1)] if idea else []) \
            + ([('process', 'Как работа рождалась', 1)] if record else []) \
            + ([('manifesto', 'Манифест замысла', 2)] if record.get('statement') else []) \
            + ([('critic', 'Внутренний критик', 2)] if record.get('interrogation') else []) \
            + ([('method', 'Выбор школы', 2)] if record.get('method') else []) \
            + [(f'draft-{n}', f'Черновик {n}', 2) for n in range(1, len(record.get('drafts') or []) + 1)] \
            + ([('hearings', 'Как слушал черновики', 2)] if record.get('entries') and hearings(record) else []) \
            + ([('reviews', 'Рецензии', 1)] if reviews else []) + [('sources', 'Первоисточники', 1)]
        plain_title = plain(final['title']) if final and final.get('title') else w['id']
        (out/f'work-{w["id"]}.html').write_text(page(plain_title, body, scripts, toc=toc))
    from .reception import VOICE, arts_of
    names = {a.id: at.name(a) for a in life.artists}
    titles = {w['id']: (w.get('title') or w['id']) for _, w in at.works()}

    def subject(r):
        kind = r.get('kind', 'work')
        if kind == 'work':
            return f'<a href="work-{r["work"]}.html">{esc(titles.get(r["work"], r["work"]))}</a>'
        if kind in ('manifesto', 'school'):
            return f'<a href="school-{html.escape(str(r["subject"]))}.html">{html.escape(school_name(r["subject"]) or str(r["subject"]))}</a>'
        return f'<a href="artist-{r["artist"]}.html">{esc(names.get(r["artist"], ""))}</a>'

    rows = ''
    for c in life.reception.critics:
        rs = [r for r in life.reception.reviews if r['critic'] == c['id']]
        avg = f'{sum(r["score"] for r in rs) / len(rs):.2f}' if rs else '—'
        rows += (f'<tr><td><a href="critic-{html.escape(c["id"])}.html">{html.escape(c["name"])}</a></td>'
                 f'<td>{html.escape(VOICE.get(c["voice"], c["voice"]))}</td>'
                 f'<td>{", ".join(ART.get(x, x) for x in arts_of(c))}</td><td>{len(rs)}</td><td>{avg}</td></tr>')
        body = (f'<h1>{html.escape(c["name"])}</h1><p class="muted">{html.escape(VOICE.get(c["voice"], c["voice"]))} · '
                f'пишет о: {", ".join(ART.get(x, x) for x in arts_of(c))} · репутация {c["reputation"]:.2f}</p>' + ''.join(
                    f'<div class="work"><b>{subject(r)}</b> <span class="muted">{GENRE_RU.get(r.get("kind", "work"))}, '
                    f'{r.get("date", "")[:10] or ("ночь " + str(r["night"]))}, оценка {r["score"]:.2f}'
                    f'{", пересмотр" if r.get("revision_of") else ""}</span>{ru_block(at, r.get("text"))}</div>'
                    for r in reversed(rs)) + ('' if rs else '<p class="muted">пока ничего не написал</p>'))
        (out/f'critic-{c["id"]}.html').write_text(page(c['name'], body))
    (out/'critics.html').write_text(page('Критики', '<h1>Критики</h1><table><tr><th>Критик</th><th>Голос</th>'
                                         '<th>Пишет о</th><th>Текстов</th><th>Средняя оценка</th></tr>' + rows + '</table>'))
    from .music.schools import SCHOOLS as MUSIC
    from .writing.schools import SCHOOLS as LETTERS
    used = {}
    for a, w in at.works():
        used.setdefault(w.get('school'), set()).add(a.id)
    def school_row(k, art, rules):
        name, about = SCHOOL_RU.get(k, (k, ''))
        authors = ', '.join(f'<a href="artist-{x}.html">{esc(at.name(at.artist(x)))}</a>' for x in sorted(used.get(k, ())))
        link = f'<a href="school-{html.escape(k)}.html">{html.escape(name)}</a>'
        return (f'<tr id="{html.escape(k)}"><td><b>{link}</b></td><td>{art}</td>'
                f'<td>{about or ru_inline(at, rules)}</td><td>{authors or "—"}</td></tr>')
    rows = ''.join(school_row(k, 'музыка', (MUSIC[k].__doc__ or '').strip().split('\n\n')[0]) for k in sorted(MUSIC))
    rows += ''.join(school_row(k, 'литература', LETTERS[k].RULES) for k in sorted(LETTERS))
    from .writing.founding import adopt
    born_letters = adopt(life)
    rows += ''.join(school_row(k, 'литература, рождена здесь', poetics.flat(poetics.load(k).get('worldview', '')))
                    for k in sorted(born_letters))
    born = ''.join(f'<div class="work" id="{html.escape(k)}"><h2>{html.escape(r["name"])}</h2><p class="muted">основал '
                   f'{html.escape(r.get("author", ""))}, ночь {r.get("night")}</p><h3>Манифест</h3><ul>' + ''.join(
                       f'<li>{ru_inline(at, m)}</li>' for m in r.get('manifesto', {}).get('manifesto', []))
                   + (f'</ul><p><a href="school-{html.escape(k)}.html">поэтика школы</a></p></div>' if r.get('art') == 'literature' else
                      f'</ul><details><summary>устав школы в коде</summary><pre class="muted">'
                      f'{html.escape(r.get("source", ""))}</pre></details></div>') for k, r in life.schools.items())
    asked = ''.join(f'<div class="work"><h2>«{ru_inline(at, s["proposal"]["school"])}»</h2><p class="muted">'
                    f'<a href="artist-{s["artist"]}.html">{esc(at.name(at.artist(s["artist"])))}</a>, ночь {s["night"]}, '
                    f'{ART.get(s.get("art"), s.get("art") or "")} · '
                    f'{ {"requested": "заявлена, ждёт ночи основания", "born": "основана", "unborn": "не родилась"}.get(s["status"], s["status"])}'
                    f'</p>{ru_block(at, s["proposal"].get("reason"))}</div>' for s in life.school_attempts if s.get('proposal'))
    (out/'schools.html').write_text(page('Школы', '<h1>Школы</h1><p class="muted">Школы — это формы, в которых творцы '
                                         'работают. Каждая записана кодом: она задаёт каркас работы и проверяет форму, '
                                         'но никогда не пишет слов и не судит о ценности. Админ кластера школы не выбирает.'
                                         '</p><table><tr><th>Школа</th><th>Искусство</th><th>О чём</th><th>Кто в ней работал</th></tr>'
                                         + rows + '</table>'
                                         + (f'<h1>Рождённые в мастерской</h1>{born}' if born else '')
                                         + (f'<h1>Заявленные школы</h1><p class="muted">Творец решил, что ни одна школа не '
                                            'держит его замысел, и заявил свою.</p>' + asked if asked else '')))
    rules = {**{k: (MUSIC[k].__doc__ or '').strip().split('\n\n')[0] for k in MUSIC},
             **{k: LETTERS[k].RULES for k in LETTERS}, **{k: v.RULES for k, v in born_letters.items()}}
    for k in rules:
        p = poetics.load(k) or {'name': SCHOOL_RU.get(k, (k, ''))[0],
                                'worldview': SCHOOL_RU.get(k, ('', ''))[1] + ' Подробная поэтика ещё не записана.'}
        def said(value):
            if isinstance(value, list):
                return '<ul>' + ''.join(f'<li>{ru_inline(at, poetics.flat(v))}</li>' for v in value) + '</ul>'
            if isinstance(value, dict):
                return ''.join(said(v) for v in value.values())
            return ru_block(at, str(value).strip())
        sections = ''.join(f'<h2>{label}</h2>{said(p[key])}' for key, label in poetics.labels(k) if p.get(key))
        lineage = p.get('lineage') or {}
        roots = ''.join(f'<dt>{t}</dt><dd>{said(lineage[key])}</dd>'
                        for key, t in (('predecessors', 'Предшественники'), ('neighbours', 'Соседи'),
                                       ('against', 'Против чего')) if lineage.get(key))
        works = ''.join(f'<li><a href="work-{w["id"]}.html">{esc(w.get("title") or w["id"])}</a> — '
                        f'{esc(at.name(a))}, ночь {w["night"]}</li>' for a, w in live if w.get('school') == k)
        founded = life.schools.get(k)
        origin = (f'основал <a href="artist-{founded["author"]}.html">{esc(at.name(at.artist(founded["author"])))}</a>, '
                  f'ночь {founded["night"]}, {founded["date"][:10]}' if founded else html.escape(poetics.flat(p.get("origin", {}))))
        body = (f'<h1>{ru_inline(at, p["name"])}</h1><p class="muted">{origin}</p>'
                + '<h2>Манифест</h2><ol class="lead">' + ''.join(f'<li>{ru_inline(at, m)}</li>' for m in p.get('manifesto', []))
                + '</ol>' + (f'<h2>Родословная</h2><dl>{roots}</dl>' if roots else '') + sections
                + f'<h2>Форма, которую проверяет код</h2><p>{html.escape(rules[k])}</p>'
                + f'<h2>Работы мастерской в этой школе</h2><ul>{works or "<li class=muted>пока нет</li>"}</ul>')
        (out/f'school-{k}.html').write_text(page(p['name'], body))
    restore_page(at, out)
    lexicon_pages(at, out, {w['id'] for _, w in live})
    names = {a.id: at.name(a) for a in life.artists}
    rows = ''.join(f'<tr><td>{e["date"][:10]}</td><td>{e["night"]}</td><td><a href="artist-{e["artist"]}.html">'
                   f'{esc(names.get(e["artist"], e["artist"]))}</a></td><td>{e["kind"]}</td></tr>' for e in life.events)
    (out/'timeline.html').write_text(page('Хронология', '<h1>Хронология</h1><table>' + rows + '</table>'))
    working = ', '.join(f'<a href="artist-{a.id}.html">{esc(at.name(a))}</a>' for a in life.working())
    body = (f'<h1>Мастерская {html.escape(life.cluster)}</h1><p class="muted">ночь {life.night} · {life.date()[:10]}</p>'
            f'<p>Работают: {working}</p><p>Творцов за всю историю: {len(life.artists)}, работ: '
            f'{sum(len(a.catalogue) for a in life.artists)}, живых работ: {len(live)}, рецензий: '
            f'{len(life.reception.reviews)}, событий: {len(life.events)}.</p>')
    (out/'index.html').write_text(page(f'Мастерская {life.cluster}', body))
    return out


def lex_page(eid):
    return 'lex-' + eid.replace(':', '-') + '.html'


def source_href(sid, meta, works):
    kind, rest = sid.split(':', 1)
    if kind == 'work':
        return f'work-{rest}.html'
    if kind == 'notebook':
        return f'work-{rest}.html' if rest in works else f'night-{rest}.html'
    if kind == 'review':
        return f'critic-{meta.get("critic")}.html'
    if kind == 'lives':
        return f'artist-{meta.get("artist")}.html'
    if kind == 'school':
        return f'school-{rest}.html'
    return '#'


def lexicon_pages(at, out, works):
    """The Lexicon: an index by kind and a page per entry, names linked, sources cited, old editions kept."""
    from .lexicon import CITE, IN, OUT, TOPICS, TYPES, Index
    entries = {k: e for k, e in at.lexicon.get('entries', {}).items() if not e.get('gone') and e.get('paragraphs')}
    registry = at.lexicon.get('sources', {})
    index = Index.of_entries(entries)

    def linked(text, me):
        parts, pos = [], 0
        for s, e, eid in index.link(text):
            if eid == me or eid not in entries:
                continue
            parts.append(html.escape(text[pos:s]) + f'<a href="{lex_page(eid)}">{html.escape(text[s:e])}</a>')
            pos = e
        return ''.join(parts) + html.escape(text[pos:])

    def href(sid):
        return html.escape(source_href(sid, registry.get(sid, {}), works))

    def title(sid):
        return html.escape(registry.get(sid, {}).get('title', sid))

    def prose(p, me):
        numbers = {sid: n for n, sid in enumerate(p.get('sources', []), 1)}
        parts, pos = [], 0
        for m in CITE.finditer(p['text']):
            sid = m.group(1)
            parts.append(linked(p['text'][pos:m.start()], me) +
                         f'<sup><a href="{href(sid)}" title="{title(sid)}">[{numbers.get(sid, sid)}]</a></sup>')
            pos = m.end()
        parts.append(linked(p['text'][pos:], me))
        cited = ''.join(f'<li><a href="{href(sid)}">{title(sid)}</a> <span class="muted">{html.escape(sid)}</span></li>'
                        for sid in p.get('sources', []))
        return f'<p>{"".join(parts)}</p><ol class="muted">{cited}</ol>'

    groups = {}
    for eid, e in entries.items():
        groups.setdefault(e['type'], []).append((e['name'].casefold(), eid))
    body = ['<h1>Словарь мастерской</h1><p class="muted">Статьи о творцах, работах, школах, критиках, о местах, вещах '
            'и лицах из работ и о событиях жизни мастерской. Каждая статья ссылается на первоисточники; абзац '
            'переписывается, только когда изменились его источники, и прежние издания статьи остаются.</p>']
    for kind in TYPES:
        if groups.get(kind):
            body.append(f'<h2>{html.escape(TYPES[kind].capitalize())}</h2><ul>' + ''.join(
                f'<li><a href="{lex_page(eid)}">{esc(entries[eid]["name"])}</a>'
                f'<span class="muted"> · издание {entries[eid]["edition"]}</span></li>' for _, eid in sorted(groups[kind]))
                + '</ul>')
    if not entries:
        body.append('<p class="muted">Словарь ещё не написан.</p>')
    (out/'lexicon.html').write_text(page('Словарь', ''.join(body)))
    for eid, e in entries.items():
        links = {}
        for r in e.get('relations', []):
            mine = r['from'] == eid
            other = r['to'] if mine else r['from']
            if other in entries:
                links.setdefault((OUT if mine else IN).get(r['type'], r['type']), set()).add(other)
        related = ''.join(f'<dt>{html.escape(label)}</dt><dd>' + ', '.join(
            f'<a href="{lex_page(x)}">{esc(entries[x]["name"])}</a>' for x in sorted(xs, key=lambda x: entries[x]['name']))
            + '</dd>' for label, xs in sorted(links.items()))
        old = ''.join(f'<details><summary>издание {ed["edition"]}{", " + ed["date"][:10] if ed.get("date") else ""}'
                      f'</summary>' + ''.join(f'<h4>{TOPICS.get(p["topic"], p["topic"])}</h4>{prose(p, eid)}'
                                              for p in ed['paragraphs']) + '</details>'
                      for ed in reversed(e.get('editions', [])))
        gloss = e.get('facts', {}).get('gloss')
        text = (f'<h1>{esc(e["name"])}</h1><p class="muted">{html.escape(TYPES.get(e["type"], e["type"]))} · '
                f'издание {e["edition"]}{", " + e["revised"][:10] if e.get("revised") else ""}</p>'
                + (f'<p class="lead">{esc(gloss)}</p>' if gloss else '')
                + ''.join(f'<h2>{TOPICS.get(p["topic"], p["topic"])}</h2>{prose(p, eid)}' for p in e['paragraphs'])
                + (f'<h2>Связи</h2><dl>{related}</dl>' if related else '')
                + (f'<h2>Прежние издания</h2>{old}' if old else ''))
        (out/lex_page(eid)).write_text(page(e['name'], text))


def restore_page(at, out):
    ledger_path = at.home/'ledger'/'ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'pieces': []}
    rows = ''.join(f'<tr><td>{"ключевой кадр" if p["kind"] == "keyframe" else "изменения"}</td><td>{p["at"][:10]}</td>'
                   f'<td>{p["bytes"]} байт</td><td>{p["carried"]} из {p["target"]}</td>'
                   f'<td>{"собран" if p["complete"] else "ещё вплетается"}</td></tr>' for p in ledger['pieces'])
    complete = [p for p in ledger['pieces'] if p['complete']]
    status = (f'Кластер можно восстановить на любой момент с {complete[0]["at"][:10]} по {complete[-1]["at"][:10]}.'
              if complete else 'Пока ни один снимок не вплетён целиком: кластер из этих работ ещё не восстанавливается. '
              'Первый снимок (ключевой кадр) — самый большой; дальше идут только изменения, и они вплетаются быстро.')
    from shutil import copyfile
    # A night keeps its carriers in woven/; a continuous life, in creators/<id>/<session>/woven/.
    carriers = sorted({p for night in at.nights for p in night.rglob('*')
                       if p.is_file() and p.parent.name == 'woven'})
    for p in carriers:
        (out/'files'/p.relative_to(at.root)).parent.mkdir(parents=True, exist_ok=True)
        copyfile(p, out/'files'/p.relative_to(at.root))
    # The owner takes every carrier at once: hundreds of links are not a way to rescue a cluster.
    import tarfile
    with tarfile.open(out/'carriers.tar.gz', 'w:gz') as archive:
        for p in carriers:
            archive.add(p, arcname=str(Path('carriers')/p.relative_to(at.root)))
    body = f"""<h1>Восстановление</h1>
<p class="lead">Работы мастерской — одновременно резервная копия кластера. Не данные томов, а состояние кластера:
все объекты API (инстансы, сервисы, настройки) на определённый момент. Копия зашифрована ключом владельца и разрезана
на куски, а куски вплетены в ноты, варианты слов и отклик публики. Восстановить можно на любой сохранённый момент.</p>
<h2>Состояние копии</h2><p>{status}</p>
<table><tr><th>Снимок</th><th>Момент</th><th>Размер</th><th>Вплетено кадров</th><th>Состояние</th></tr>{rows}</table>
<p class="muted">Кадров нужно больше исходного числа: копия переживает потерю до 30% работ.</p>
<h2>Как поднять кластер</h2>
<ol>
<li><b>Ключ владельца.</b> Его создают один раз командой <code>mnemo keys new --output DIR</code>. Файл
<code>owner.key</code> хранится у владельца вне кластера; в кластер уходит только открытая часть. Без этого ключа
работы читаются как искусство, но копия из них не извлекается.</li>
<li><b>Работы.</b> Все носители одним архивом: <a href="carriers.tar.gz">carriers.tar.gz</a>
(сейчас носителей: {len(carriers)}). Распакуйте его: <code>tar xzf carriers.tar.gz</code>. Носители есть и по одному —
в списке ниже и в разделе «Первоисточники» на страницах работ.</li>
<li><b>Проверка без кластера.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --dry-run --at 2025-06-30T23:59:59Z</pre>
Команда собирает куски, проверяет подписи, расшифровывает и пишет манифесты состояния на этот момент в новую папку.
Без <code>--at</code> берётся самое новое состояние.</li>
<li><b>Применение.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --apply --kubeconfig new.kubeconfig --context new</pre>
Манифесты применяются к новому кластеру. Секреты по умолчанию не восстанавливаются; их включает
<code>--include-secrets</code>, если владелец разрешил их в копии.</li>
</ol>
<h2>Носители</h2><ul class="muted">{''.join(f'<li><a href="files/{html.escape(str(p.relative_to(at.root)))}">{html.escape(p.name)}</a></li>'
    for p in carriers)}</ul>"""
    (out/'restore.html').write_text(page('Восстановление', body))


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
