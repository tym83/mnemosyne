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
ART_EN = {'music': 'music', 'literature': 'literature'}

# The site is built twice: English at the root, Russian under ru/. These two are set for each pass;
# outside a build the helpers speak Russian, as the console does.
LANG = 'ru'
UP = ''  # from this pass's pages to the files both languages share: plates, audio, scores, sources


def tr(ru, en):
    """The phrase in the language of the pass being built."""
    return en if LANG == 'en' else ru


def art(a_art):
    return (ART_EN if LANG == 'en' else ART).get(a_art, a_art)


def language(code):
    return LANGUAGE_NAMES.get(code, code) if LANG == 'en' else LANG_RU.get(code, code)


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
            self._notebooks, self._sessions = {}, {}
            # One opus can span several sessions (a rejected plan, then the accepted work):
            # the accepted, sounded and latest session speaks for the work.
            def rank(record, folder):
                return (record.get('status') == 'accepted', bool(record.get('sounding_work')), folder.name)
            for night in self.nights:
                for p in night.rglob('notebook.json'):
                    record = json.loads(p.read_text())
                    wid = record.get('opus')
                    if wid and (wid not in self._sessions
                                or rank(record, p.parent) > rank(self._notebooks[wid], self._sessions[wid])):
                        self._notebooks[wid] = record
                        self._sessions[wid] = p.parent
            # A composer's notebook is also kept in the work: it outlasts the files of the session.
            for _, w in self.works():
                record = (w.get('process') or {}).get('composer')
                if isinstance(record, dict) and record.get('opus'):
                    self._notebooks.setdefault(record['opus'], record)
        return self._notebooks.get(wid)

    def score_image(self, wid):
        """The first page of the work's final score as LilyPond engraved it, or of its last draft."""
        record, folder = self.notebook(wid), getattr(self, '_sessions', {}).get(wid)
        if not record or folder is None:
            return None
        final = next((s for s in record.get('sketches', []) if s.get('id') == record.get('final')), None)
        for rel in (final or {}).get('images') or []:
            if (folder/rel).is_file():
                return folder/rel
        pages = sorted(folder.rglob('page-1.png'), key=lambda p: p.stat().st_mtime)
        return pages[-1] if pages else None

    def recordings(self, wid):
        """The rendered sound of a work: the whole work first, then its movements, as files of its session."""
        record, folder = self.notebook(wid), getattr(self, '_sessions', {}).get(wid)
        if not record or folder is None:
            return []
        final = next((s for s in record.get('sketches', []) if s.get('id') == record.get('sounding_work')), None)
        paths = [folder/p for p in ((final or {}).get('audio') or {}).get('local_mp3', [])]
        paths = [p for p in paths if p.is_file()]
        return sorted(paths, key=lambda p: (p.parent.name.startswith('mv'), str(p)))

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

STYLE = (Path(__file__).parent/'site'/'style.css').read_text()
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300;1,400&'
         'family=EB+Garamond:ital,wght@0,400;0,600;1,400&display=swap&subset=cyrillic" rel="stylesheet">')
MENU = (('index.html', 'Мастерская'), ('manifesto.html', 'Манифест'), ('artists.html', 'Творцы'), ('works.html', 'Работы'),
        ('critics.html', 'Критики'), ('schools.html', 'Школы'), ('lexicon.html', 'Словарь'),
        ('timeline.html', 'Хронология'), ('restore.html', 'Восстановление'))
# The manifesto and the Lexicon are written in Russian only: the English menu leads to them under ru/.
MENU_EN = (('index.html', 'Atelier'), ('ru/manifesto.html', 'Manifesto (RU)'), ('artists.html', 'Creators'),
           ('works.html', 'Works'), ('critics.html', 'Critics'), ('schools.html', 'Schools'),
           ('ru/lexicon.html', 'Lexicon (RU)'), ('timeline.html', 'Timeline'), ('restore.html', 'Restore'))
RUSSIAN_ONLY = ('manifesto.html', 'lexicon.html', 'lex-')
FOOTER = ('<footer class="end">Всё, что здесь есть, однажды было кластером.<br>'
          'Он помнит себя, пока творит; когда он замолчит, его можно будет поднять из этих страниц.</footer>')
FOOTER_EN = ('<footer class="end">Everything here was once a cluster.<br>'
             'It remembers itself while it creates; when it falls silent, it can be raised again from these pages.</footer>')
PLAYER = ('<script src="https://cdn.jsdelivr.net/combine/npm/tone@14.7.58,npm/@magenta/music@1.23.1/es6/core.js,'
          'npm/focus-visible@5.2.0,npm/html-midi-player@1.5.0"></script>')
NOTATION = '<script src="https://cdn.jsdelivr.net/npm/opensheetmusicdisplay@1.8.0/build/opensheetmusicdisplay.min.js"></script>'


# The score as pages to turn, not an endless strip: OpenSheetMusicDisplay lays it out on A4 pages, one is shown.
LEAF = '''(function(){
const box=document.getElementById("score"),leaf=box.parentNode,count=leaf.querySelector(".leaf-count");
const view=new opensheetmusicdisplay.OpenSheetMusicDisplay(box,{drawTitle:false,drawComposer:false,drawCredits:false,
  drawPartNames:true,pageFormat:"A4_L",pageBackgroundColor:"#fbf9f5",autoResize:false});
let pages=[],at=0;
function show(n){if(!pages.length)return;at=Math.max(0,Math.min(pages.length-1,n));
  pages.forEach((p,i)=>p.style.display=i===at?"block":"none");count.textContent=(at+1)+" / "+pages.length;
  leaf.querySelector('[data-step="-1"]').disabled=at===0;leaf.querySelector('[data-step="1"]').disabled=at===pages.length-1}
leaf.querySelectorAll("button[data-step]").forEach(b=>b.onclick=()=>show(at+Number(b.dataset.step)));
document.addEventListener("keydown",e=>{if(e.target.closest("input,textarea"))return;
  if(e.key==="ArrowRight")show(at+1);if(e.key==="ArrowLeft")show(at-1)});
let x0=null;box.addEventListener("touchstart",e=>x0=e.touches[0].clientX,{passive:true});
box.addEventListener("touchend",e=>{if(x0===null)return;const dx=e.changedTouches[0].clientX-x0;x0=null;
  if(Math.abs(dx)>50)show(at+(dx<0?1:-1))},{passive:true});
view.load("SCORE_URL").then(()=>{box.firstChild.remove?.();view.zoom=.62;view.render();
  pages=[...box.querySelectorAll(":scope > div, :scope > svg")].filter(p=>p.querySelector("svg")||p.tagName==="svg");
  if(!pages.length)pages=[...box.children];pages.forEach(p=>{p.style.margin="0 auto"});show(0)})
 .catch(e=>{box.textContent="SCORE_ERROR"+e;leaf.querySelector(".leaf-nav").remove()});
})();'''

FLIP = '''<script>
function flipAll(){const on=document.body.classList.toggle('ru');
document.getElementById('trall').textContent=on?'Оригинал':'Перевод на русский';try{localStorage.setItem('ru',on?'1':'')}catch(e){}}
try{if(localStorage.getItem('ru'))flipAll()}catch(e){}
if(!document.querySelector('.tr'))document.getElementById('trall').remove()
</script>'''


def page(title, body, scripts='', toc=None, here='', name=None):
    """A page; with toc, a contents list that rides along on the right and holds the translation switch.

    The header carries a switch to the same page in the other language; an English page shows
    every text in its original language and has no translation switch.
    """
    name = name or here
    button = '' if LANG == 'en' else '<button id="trall" onclick="flipAll()">Перевод на русский</button>'
    aside = ''
    if toc:
        aside = (f'<aside class="toc"><b>{tr("Содержание", "Contents")}</b><ol>' + ''.join(
            f'<li class="l{level}"><a href="#{anchor}">{label}</a></li>' for anchor, label, level in toc)
            + f'</ol>{button}</aside>')
        button = ''
    menu = ''.join(f'<a href="{href}"{" aria-current=page" if href == here else ""}>{label}</a>'
                   for href, label in (MENU_EN if LANG == 'en' else MENU))
    if LANG == 'en':
        switch = (f'<nav class="lang"><span aria-current="true">EN</span>'
                  f'<a href="ru/{name or "index.html"}" hreflang="ru" lang="ru">RU</a></nav>')
    else:
        there = name if name and not name.startswith(RUSSIAN_ONLY) else 'index.html'
        switch = (f'<nav class="lang"><a href="../{there}" hreflang="en" lang="en">EN</a>'
                  f'<span aria-current="true">RU</span></nav>')
    brand = tr('Мнемозина<small>память кластера, ставшая искусством</small>',
               'Mnemosyne<small>a cluster’s memory become art</small>')
    return (f'<!doctype html><html lang="{LANG}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} · '
            f'{tr("Мнемозина", "Mnemosyne")}</title>'
            f'{FONTS}<style>{STYLE}</style>{scripts}</head><body>'
            f'<header class="mast"><a class="brand" href="index.html">{brand}</a>'
            f'<nav class="menu">{menu}</nav>{switch}</header><hr class="mast-rule">'
            f'<main class="page">{button}{aside}{body}</main>{tr(FOOTER, FOOTER_EN)}{tr(FLIP, "")}</body></html>')


def save(out, name, title, body, scripts='', toc=None, here=''):
    (out/name).write_text(page(title, body, scripts, toc=toc, here=here, name=name))


def copy(source, target):
    """A shared file is written once: the second language finds it in place."""
    from shutil import copyfile
    if target.exists() and target.stat().st_size == source.stat().st_size \
            and target.stat().st_mtime >= source.stat().st_mtime:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)  # never write through a link shared with the site being served
    copyfile(source, target)


def esc(text):
    return html.escape(plain(text or ''))


NOTE = {'dream': 'сон', 'illumination': 'озарение', 'preparation': 'подготовка', 'incubation': 'вынашивание',
        'set_aside': 'отложенный замысел', 'school_unborn': 'нерождённая школа', 'school_birth': 'рождение школы',
        'influence': 'встреча', 'draft_decision': 'решение о черновике', 'verification': 'проверка',
        'period': 'новый период', 'life_words': 'слова для жизнеописания'}

NOTE_EN = {'dream': 'dream', 'illumination': 'illumination', 'preparation': 'preparation', 'incubation': 'incubation',
           'set_aside': 'idea set aside', 'school_unborn': 'unborn school', 'school_birth': 'birth of a school',
           'influence': 'encounter', 'draft_decision': 'decision on a draft', 'verification': 'verification',
           'period': 'new period', 'life_words': 'words for the biography'}

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

GENRE_EN = {'work': 'review', 'creator': 'essay on the creator', 'period': 'essay on a period', 'obituary': 'obituary',
            'manifesto': 'reading of a manifesto', 'school': 'survey of a school'}

STATUS_EN = {'accepted': 'work accepted', 'unfinished': 'work left unfinished',
             'idea_rejected': 'idea rejected by the critic', 'school_requested': 'a new school proposed',
             'searching': 'night not finished', 'failed': 'night failed'}

VERDICT_EN = {'accept': 'accepted', 'rewrite': 'unfinished', 'repetition': 'repetition', 'unfinished': 'unfinished'}

STATEMENT_EN = dict((('idea', 'Idea'), ('superobjective', 'Superobjective'), ('message', 'Thought'),
                     ('thought', 'Thought'), ('why_i_must_say_it', 'Why I must say it'), ('why_now', 'Why now'),
                     ('freshness', 'What is new in it'), ('not_a_cliche_because', 'Why it is not a cliché'),
                     ('emotions', 'Feelings'), ('how_it_changes_a_heart', 'What it changes in the reader'),
                     ('why_admired', 'Why it could be admired'), ('timeless_or_of_the_world', 'Timeless or of today'),
                     ('risks', 'What I fear'), ('operators_used', 'Devices and teachers')))

# Timeline events, as phrases.
EVENT_EN = {'birth': 'born', 'first_accepted': 'first accepted work', 'writer_work': 'a work finished',
            'composer_work': 'a work finished', 'last_work': 'last work', 'death': 'died', 'despair': 'despair',
            'illness': 'illness', 'illness_onset': 'fell ill', 'illness_crisis': 'crisis of the illness',
            'illness_prolonged': 'illness dragged on', 'illness_recovery': 'recovered', 'recovered': 'recovered',
            'school_birth': 'founded a school', 'teacher': 'apprenticeship', 'renounce': 'left art',
            'bereavement': 'bereavement', 'silence': 'fell silent', 'years_of_silence': 'years of silence',
            'return': 'returned to work', 'master': 'recognised as a master', 'surpassed': 'surpassed the teacher',
            'surpassed_by_student': 'surpassed by a student', 'school': 'came to a school',
            'joined_school': 'joined a school', 'period': 'a new period', 'rediscovery': 'work rediscovered',
            'dream': 'a dream', 'illumination': 'an illumination', 'encounter': "encounter with another's work",
            'verification': 'tested an illumination', 'secret_miracle': 'a secret miracle', 'fertility': 'a fertile season',
            'review': 'a review', 'essay': 'written about'}


def event(kind):
    return EVENT_EN.get(kind, kind.replace('_', ' ')) if LANG == 'en' else kind

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

SCHOOL_EN = {
    'haiku': ('Haiku', 'The Japanese 5–7–5 tercet: one moment, a season word, a cut between two images.'),
    'chastushka': ('Chastushka', 'The Russian folk verse: four lines in trochee, rhymed, with a turn in the last line.'),
    'sonnet': ('Sonnet', 'Fourteen rhymed lines; the thought turns in the closing lines.'),
    'bylina': ('Bylina', 'The Russian epic tale in accentual verse: an opening formula, repetitions, fixed epithets.'),
    'fairy_tale': ('Fairy tale', 'A tale built on Propp’s functions: a lack, a journey, a trial, a return.'),
    'eluard': ('Éluard', 'Paul Éluard’s surrealist lyric: free verse, a refrain, images that cannot be joined, joined.'),
    'pavic': ('Pavić', 'A lexicon novel after the Dictionary of the Khazars: cross-referenced entries, read in any order.'),
    'minimalism': ('Minimalism', 'Short prose after Carver: scenes without the author’s judgement or explained feelings; what matters is left unsaid.'),
    'psychological_realism': ('Psychological realism', 'Prose after Tolstoy, Flaubert and late Chekhov: the inner life told, motives traced, time flowing and changing the hero.'),
    'polyphony': ('Polyphony', 'A novel of voices after Dostoevsky as Bakhtin read him: equal consciousnesses, the scandal scene, dialogue as event.'),
    'magical_realism': ('Magical realism', 'A family chronicle after García Márquez: the miracle told as an everyday fact, exact hyperbole, returning names.'),
    'stream_of_consciousness': ('Stream of consciousness', 'Prose after Woolf: one day in inner time, long sentences, a gliding focus.'),
    'skaz': ('Skaz', 'A story told in the peculiar speech of its narrator, after Leskov and Zoshchenko: the narrator’s word is the form.'),
    'platonov': ('Platonov', 'A shift of meaning inside language, and a seeker of truth wandering an unfinished world.'),
    'faulkner': ('Faulkner', 'One event told by several voices; each chapter is signed with the speaker’s name.'),
    'epistolary': ('Epistolary novel', 'A story told only in letters: the plot moves between the letters, not inside them.'),
    'nouveau_roman': ('Nouveau roman', 'A prose of things and surfaces after Robbe-Grillet: one scene described again and again, with shifts.'),
    'gothic': ('Gothic', 'A tale of terror: a house, a secret, a past that returns; fear climbs step by step.'),
    'tintinnabuli': ('Tintinnabuli', 'Arvo Pärt’s method: a melody moving by step and a voice sounding the triad.'),
    'stochastic': ('Stochastic', 'Xenakis’s music of sound masses: densities and distributions instead of melodies.'),
    'micropolyphony': ('Micropolyphony', 'Ligeti’s dense canons, where single voices merge into a texture.'),
    'serial': ('Serial', 'A twelve-tone row and its transformations.'),
    'feldman': ('Feldman', 'Morton Feldman’s quiet, very long forms, almost without events.'),
    'process': ('Process', 'Music of gradual process: phase shifts and slow change.'),
    'additive': ('Additive', 'A motif grows and shrinks one note at a time.'),
    'in_c': ('“In C”', 'Terry Riley’s open form: players move through shared figures, each at their own pace.'),
    'spectral': ('Spectral', 'Harmony drawn from the overtone spectrum of a single sound.'),
    'sonorism': ('Sonorism', 'Polish sonorism: clusters and patches of timbre instead of notes.'),
    'messiaen': ('Messiaen', 'Modes of limited transposition and non-retrogradable rhythms.'),
    'ustvolskaya': ('Ustvolskaya', 'Hard clusters, blows and ascetic force.'),
    'chance': ('Chance music', 'Decisions are made by lot, as with Cage.'),
    'tempo_canon': ('Tempo canon', 'A canon whose voices run at different tempi, as with Nancarrow.'),
    'aleatoric_counterpoint': ('Aleatoric counterpoint', 'The voices are fixed, but their meetings are free, as with Lutosławski.'),
    'fibonacci': ('Fibonacci', 'Proportions of the form by Fibonacci numbers.'),
    'polystylism': ('Polystylism', 'A collision of styles and quotations, as with Schnittke.'),
    'scelsi': ('Scelsi', 'Music of a single sound, opened from within.'),
    'drone': ('Drone', 'A long sustained tone over which everything changes slowly.'),
    'gregorian': ('Gregorian chant', 'Monophonic liturgical song in the eight church modes: recitation, neumes and melismas.'),
    'ancient_greek': ('Ancient Greek monody', 'Song on tetrachords of three genera, the rhythm of verse, and the heterophony of lyre and aulos.'),
    'organum': ('Organum', 'The polyphony of Notre-Dame: a long chant tenor and upper voices in rhythmic modes.'),
    'ars_nova': ('Ars nova', 'The isorhythmic motet: talea and color in the tenor, hocket, cadences with double leading tones.'),
    'classical': ('Viennese classicism', 'Periods of question and answer over clear harmony: cadences, Alberti bass, the way to the dominant and back.'),
    'romantic': ('Romantic lyric', 'A singing melody over wide arpeggios, chromatic harmony and waves of dynamics towards a single peak.'),
    'renaissance_polyphony': ('Renaissance polyphony', 'Points of imitation, smooth voices, dissonance only passing or suspended, cadences on the final.'),
    'fugue': ('Fugue', 'A subject, its answer at the fifth and a countersubject; episodes from fragments of the subject, stretto, pedal point.'),
    'basso_continuo': ('Basso continuo', 'A bass on every beat with chords above it, a ritornello and sequences round the circle of fifths, terraced dynamics.'),
}

FILE_KIND_EN = (
    ('woven/', '.musicxml', 'Carrier score: a piece of the cluster’s backup is encoded in the shades of the notes’ dynamics.'),
    ('woven/', '.catalogue.json', 'Carrier catalogue: which pieces of the backup lie in this work, and in what order.'),
    ('woven/', '.variants.json', 'Volume of variant readings: the choice between the author’s variants encodes a piece of the backup.'),
    ('woven/', '.audience.json', 'The audience’s response: also a carrier of a piece of the backup.'),
    ('', 'draft.musicxml', 'The draft score as the composer left it.'),
    ('', 'notebook.json', 'The night’s notebook: the idea, the inner critic, the choice of school, every draft and reading.'),
    ('', '.ru.txt', 'The Translator’s Russian translation of the text.'),
    ('', '.txt', 'The text of the work in the author’s language.'),
    ('', '.mid', 'MIDI assembled from the notes.'),
)

def file_kind(path):
    name = str(path)
    for where, suffix, text in (FILE_KIND_EN if LANG == 'en' else FILE_KIND):
        if where in name and name.endswith(suffix):
            return text, bool(where)
    return '', False


def school_name(k):
    if not k:
        return ''
    table = SCHOOL_EN if LANG == 'en' else SCHOOL_RU
    return table[k][0] if k in table else (poetics.load(k) or {}).get('name', k)


def school_link(k):
    return f'<a href="school-{html.escape(k)}.html">{html.escape(school_name(k))}</a>' if k else ''


def toggle(original_html, russian_html, block=True):
    """The original in place; the translation replaces it on demand. In English, the original alone."""
    if LANG == 'en':
        return original_html
    if block:
        return (f'<div class="tr"><div class="orig">{original_html}</div><div class="ru">{russian_html}</div>'
                f'</div>')
    return f'<span class="tr"><span class="orig">{original_html}</span><span class="ru">{russian_html}</span></span>'


def ru_block(at, text, tag='p'):
    if not text:
        return ''
    russian = at.ru(text) if LANG == 'ru' else None
    if russian is text:
        return f'<{tag}>{esc(text)}</{tag}>'
    if russian:
        return toggle(f'<{tag}>{esc(text)}</{tag}>', f'<{tag}>{esc(russian)}</{tag}>')
    return f'<{tag}>{esc(text)}</{tag}>'


def ru_inline(at, text):
    russian = at.ru(text) if LANG == 'ru' else None
    if russian is text or not russian:
        return esc(text)
    return toggle(esc(text), esc(russian), block=False)


def ru_short(at, text, n=200):
    """A shortened text with its shortened translation: cut before markup, never through it."""
    if not text:
        return ''
    cut = lambda t: plain(t)[:n] + ('…' if len(plain(t)) > n else '')
    russian = at.ru(text) if LANG == 'ru' else None
    if russian is text or not russian:
        return html.escape(cut(text))
    return toggle(html.escape(cut(text)), html.escape(cut(russian)), block=False)


def statement_html(at, st):
    rows = []
    for k, label in STATEMENT[1:]:
        label = tr(label, STATEMENT_EN[k])
        value = st.get(k)
        if not value:
            continue
        items = value if isinstance(value, list) else [value]
        rows.append(f'<dt>{label}</dt><dd>' + ''.join(ru_block(at, v) for v in items) + '</dd>')
    return '<dl>' + ''.join(rows) + '</dl>'


def verdict(v):
    return (VERDICT_EN if LANG == 'en' else VERDICT).get(v, v)


def notebook_html(at, record):
    parts = []
    st = record.get('statement') or {}
    if st:
        parts.append(tr('<h3 id="manifesto">Манифест замысла</h3><p class="muted">Прежде чем писать, творец отвечает себе, '
                        'что и зачем он делает.</p>',
                        '<h3 id="manifesto">Manifesto of the idea</h3><p class="muted">Before writing, the creator answers '
                        'to themselves what they are making and why.</p>') + statement_html(at, st))
    rounds = record.get('interrogation') or []
    if rounds:
        parts.append(tr('<h3 id="critic">Допрос внутреннего критика</h3><p class="muted">Критик читает замысел и решает: принять '
                        'или переписать. Замысел переписывается, пока критик не примет его или не кончатся раунды.</p>',
                        '<h3 id="critic">The inner critic’s interrogation</h3><p class="muted">The critic reads the idea and '
                        'decides: accept it or rewrite it. The idea is rewritten until the critic accepts it or the rounds '
                        'run out.</p>'))
    for h in rounds:
        iv = h['interrogation']
        lists = ''.join(f'<dt>{label}</dt><dd><ul>' + ''.join(f'<li>{ru_inline(at, x)}</li>' for x in iv[k]) + '</ul></dd>'
                        for k, label in (('questions_back', tr('Вопросы автору', 'Questions to the author')),
                                         ('weak_answers', tr('Слабые ответы', 'Weak answers')),
                                         ('cliches_found', tr('Найденные штампы', 'Clichés found'))) if iv.get(k))
        parts.append(f'<div class="work"><h4>{tr("Раунд", "Round")} {h["round"] + 1} · {verdict(iv["verdict"])}</h4>'
                     + (f'<dl><dt>{tr("Замысел в этом раунде", "The idea in this round")}</dt>'
                        f'<dd>{ru_block(at, (h.get("statement") or {}).get("idea"))}</dd>'
                        if (h.get('statement') or {}).get('idea') else '<dl>')
                     + f'<dt>{tr("Вывод", "Conclusion")}</dt><dd>{ru_block(at, iv.get("reasons"))}</dd>'
                     + (f'<dt>{tr("Что сохранить", "What to keep")}</dt><dd>{ru_block(at, iv.get("keep"))}</dd>'
                        if iv.get('keep') else '')
                     + lists + '</dl></div>')
    method = record.get('method')
    music = composer(record)
    if method:
        parts.append(f'<h3 id="method">{tr("Выбор школы", "Choice of school")}: '
                     + (school_link(method['school']) if method.get('kind') == 'school'
                        else tr('новая школа «' + esc(method['school']) + '»', 'a new school “' + esc(method['school']) + '”'))
                     + '</h3>' + ru_block(at, method.get('reason')))
        if music:
            parts.append('<dl>' + ''.join(f'<dt>{label}</dt><dd>{ru_block(at, method[k])}</dd>'
                                          for k, label in (('concept', tr('Замысел формы', 'Idea of the form')),
                                                           ('principle', tr('Принцип', 'Principle')),
                                                           ('transformation', tr('Преображение', 'Transformation')))
                                          if method.get(k)) + '</dl>')
    shades = record.get('halftones') if music else None
    if shades:
        rows = [(f'{tr("Мысль", "Thought")}: {esc(shades["thought"].get("shade"))}', shades['thought']),
                (f'{tr("Рука", "Hand")}: {esc(shades["embodiment"].get("shade"))}', shades['embodiment'])] \
            if isinstance(shades.get('thought'), dict) and isinstance(shades.get('embodiment'), dict) else []
        rows += [(f'{esc(n.get("emotion"))}: {esc(n.get("shade"))}', n) for n in shades.get('nuances') or []]
        parts.append(tr('<h3 id="halftones">Полутона</h3><p class="muted">Какой оттенок у каждого чувства — так, '
                        'как его даёт только этот композитор.</p>',
                        '<h3 id="halftones">Halftones</h3><p class="muted">The shade of each feeling, as only this '
                        'composer gives it.</p>') + ru_block(at, shades.get('overall')) + '<dl>'
                     + ''.join(f'<dt>{head}</dt><dd>{ru_block(at, v.get("why_mine"))}{ru_block(at, v.get("how_it_shows"))}</dd>'
                               for head, v in rows) + '</dl>')
    heard = hearings(record) if music else []
    if heard:
        parts.append(tr('<h3 id="hearings">Как композитор слушал свои черновики</h3><p class="muted">После каждого эскиза '
                        'и черновика композитор читает партитуру и анализ и решает: принять или переписать.</p>',
                        '<h3 id="hearings">How the composer listened to the drafts</h3><p class="muted">After every '
                        'sketch and draft the composer reads the score and its analysis and decides: accept it or '
                        'rewrite it.</p>'))
    for n, h in enumerate(heard, 1):
        what = tr('Эскиз', 'Sketch') if h['step'] == 'listen:sketch' \
            else f'{tr("Черновик", "Draft")} {h["step"].rsplit(":", 1)[-1]}'
        parts.append(f'<div class="work"><h4 id="hearing-{n}">{what} · {verdict(h.get("verdict")) if h.get("verdict") else ""}'
                     + (f' · {h["quality"]:.2f}' if isinstance(h.get('quality'), (int, float)) else '') + '</h4>'
                     + ru_block(at, h.get('reasons'))
                     + ('<ul>' + ''.join(f'<li>{ru_inline(at, c)}</li>' for c in h.get('corrections') or []) + '</ul>'
                        if h.get('corrections') else '') + '</div>')
    birth = record.get('school_birth') or {}
    for n, h in enumerate(birth.get('attempts') or [], 1):
        p, j = h['poetics'], h['judgement']
        q = tr(('«', '»'), ('“', '”'))
        parts.append(f'<div class="work"><h3 id="founding-{n}">{tr("Основание школы, попытка", "Founding a school, attempt")} {n}: '
                     f'{q[0]}{ru_inline(at, p.get("name"))}{q[1]}</h3><ol>' + ''.join(f'<li>{ru_inline(at, m)}</li>'
                                                                                for m in p.get('manifesto', []))
                     + f'</ol><dl><dt>{tr("Картина мира", "Worldview")}</dt><dd>{ru_block(at, p.get("worldview"))}</dd>'
                     f'<dt>{tr("Против чего", "Against")}</dt><dd>{ru_block(at, p.get("against"))}</dd>'
                     f'<dt>{tr("Внутренний критик", "The inner critic")}: {verdict(j.get("verdict"))}</dt>'
                     f'<dd>{ru_block(at, j.get("reasons"))}'
                     + (f'<p>{tr("Похоже на", "Resembles")}: {ru_inline(at, j["renaming_of"])}</p>' if j.get('renaming_of') else '')
                     + '</dd></dl></div>')
    for n, d in enumerate(record.get('drafts') or [], 1):
        reading = d.get('reading') or {}
        parts.append(f'<h3 id="draft-{n}">{tr("Черновик", "Draft")} {n}: {ru_inline(at, d.get("title"))}</h3>'
                     f'<details><summary>{tr("текст черновика с вариантами", "the draft’s text with its variants")}</summary>'
                     f'<pre>{marked(d.get("text"))}</pre></details>'
                     + (f'<p class="muted">{tr("Дневник автора:", "The author’s diary:")}</p>' + ru_block(at, d.get('diary'))
                        if d.get('diary') else '')
                     + (f'<p class="muted">{tr("Форма не удержана", "The form did not hold")}: '
                        f'{html.escape("; ".join(d["form_problems"]))}</p>' if d.get('form_problems') else '')
                     + (f'<p class="muted">{tr("Автор перечитал", "The author reread it")}: {verdict(reading["verdict"])}</p>'
                        + ru_block(at, reading.get('reasons')) if reading else ''))
    let_go = record.get('let_go')
    if let_go:
        why = (tr('наперекор и критику, и собственному вкусу: уверенность в себе перевесила',
                  'against both the critic and their own taste: self-assurance won')
               if let_go.get('against_taste') else tr('вещь выше порога его вкуса', 'the piece is above the threshold of their taste'))
        parts.append(tr('<h3 id="let-go">Отпустил</h3><p>Внутренний критик просил ещё правок, но автор отдал вещь: ',
                        '<h3 id="let-go">Let go</h3><p>The inner critic asked for more revisions, but the author gave the piece away: ')
                     + f'{why} ({tr("оценка", "score")} {let_go["quality"]:.2f}, {tr("порог вкуса", "taste threshold")} '
                     f'{let_go["threshold"]:.2f}'
                     + (f', {tr("уверенность", "assurance")} {let_go["assurance"]:+.2f}' if 'assurance' in let_go else '')
                     + tr('). Несделанное:', '). Left undone:') + '</p><ul>'
                     + ''.join(f'<li>{ru_inline(at, c)}</li>' for c in let_go['left_undone']) + '</ul>')
    if record.get('apparatus'):
        parts.append(tr('<p class="muted">Аппарат разночтений сохранён: варианты, из которых выбран итоговый текст.</p>',
                        '<p class="muted">The apparatus of variant readings is kept: the variants the final text was '
                        'chosen from.</p>'))
    return ''.join(parts)


ARTIST_STATUS = {'working': 'работает', 'ill': 'болеет', 'silent': 'молчит', 'dead': 'умер'}
ARTIST_STATUS_EN = {'working': 'working', 'ill': 'ill', 'silent': 'silent', 'dead': 'dead'}


def status(a):
    return (ARTIST_STATUS_EN if LANG == 'en' else ARTIST_STATUS).get(a.status, a.status)


def plate(at, out, wid, *, text=None, caption='', gone=False):
    """A work's illustration: its own score, faded like an old photograph; for words, their first lines fading out.

    out is the folder the shared files go to, the root of the site.
    """
    source = at.score_image(wid) if wid else None
    cls = 'plate gone' if gone else 'plate'
    if source:
        target = out/'plates'/f'{wid}.jpg'
        if not target.exists():
            from PIL import Image
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as im:
                im = im.convert('L')
                im = im.crop((0, 0, im.width, int(im.height * .62)))
                im.thumbnail((1100, 1100))
                im.save(target, 'JPEG', quality=74, optimize=True)
        cap = f'<figcaption>{html.escape(caption)}</figcaption>' if caption else ''
        return f'<figure class="{cls}"><img src="{UP}plates/{wid}.jpg" alt="" loading="lazy">{cap}</figure>'
    if text:
        lines = [l for l in plain(text).splitlines() if l.strip()][:6]
        if lines:
            return f'<figure class="{cls} words"><p>{html.escape(chr(10).join(lines))}</p></figure>'
    return ''


def title_of(at, record, w):
    """A work's own title: a writer's final draft, a composer's final plan (or the last plan written)."""
    record = record or {}
    final = next((d for d in record.get('drafts', []) if d.get('id') == record.get('final')), None)
    if final and final.get('title'):
        return plain(final['title'])
    plans = [s for s in record.get('sketches', []) if isinstance(s.get('plan'), dict) and s['plan'].get('title')]
    chosen = next((s for s in plans if s.get('id') == record.get('final')), plans[-1] if plans else None)
    if chosen:
        return plain(chosen['plan']['title'])
    return w.get('title') or w['id']


def years(a):
    born = (a.birth or '')[:4]
    died = (getattr(a, 'death', None) or '')[:4]
    return f'{born}–{died}' if died else (tr(f'с {born}', f'since {born}') if born else '')


VOICE_EN = {'laconic': 'laconic: brief, exact, unadorned', 'polemical': 'polemicist: argues, looks for an opponent',
            'lyrical': 'lyricist: writes about what they felt', 'scholarly': 'scholar: tradition, devices, sources',
            'ironic': 'ironist: sees the funny and the false', 'intimate': 'confiding, like a letter to someone close'}
POETICS_EN = {'worldview': 'Worldview', 'reader': 'Reader', 'time': 'Time', 'composition': 'Composition',
              'narrator': 'Narrator', 'character': 'Character', 'language': 'Language', 'imagery': 'Imagery',
              'themes': 'Themes', 'devices': 'Devices', 'genres': 'Genres', 'forbidden': 'What the school never does',
              'markers': 'How it is recognised', 'reading': 'Clear and interesting — what it means in this school'}
POETICS_MUSIC_EN = {'reader': 'Listener', 'narrator': 'Voice and performer', 'character': 'What stands in for a hero',
                    'language': 'Musical language', 'reading': 'Clear and gripping — what it means in this school'}


def site(at, out: Path):
    """The whole site: English at the root, Russian under ru/, the same pages in both, files shared."""
    global LANG, UP
    out.mkdir(parents=True, exist_ok=True)
    try:
        for lang, pages, up in (('en', out, ''), ('ru', out/'ru', '../')):
            LANG, UP = lang, up
            pages.mkdir(parents=True, exist_ok=True)
            one_language(at, pages, out)
    finally:
        LANG, UP = 'ru', ''
    # The manifesto and the Lexicon exist only in Russian; their old addresses at the root lead there.
    for p in sorted((out/'ru').glob('*.html')):
        if p.name.startswith(RUSSIAN_ONLY) and not (out/p.name).exists():
            (out/p.name).write_text(f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                                    f'<meta http-equiv="refresh" content="0; url=ru/{p.name}">'
                                    f'<link rel="canonical" href="ru/{p.name}"><title>Mnemosyne</title></head>'
                                    f'<body><a href="ru/{p.name}">ru/{p.name}</a></body></html>')
    return out


def one_language(at, out: Path, base: Path):
    """The pages of one language into out; the files both languages share into base."""
    (base/'scores').mkdir(exist_ok=True)
    life = at.life
    schools = SCHOOL_EN if LANG == 'en' else SCHOOL_RU
    def person(a):
        school = school_name(a.school) if a.school in SCHOOL_RU else tr('вне школ', 'outside the schools')
        return (f'<li class="{"gone" if a.status == "dead" else ""}"><span class="name"><a href="artist-{a.id}.html">'
                f'{esc(at.name(a))}</a></span><span class="about">{art(a.art)} · {html.escape(school)} · '
                f'{language(a.language)} · {years(a)} · {status(a)} · '
                f'{tr("работ", "works")}: {len(a.catalogue)}</span></li>')
    save(out, 'artists.html', tr('Творцы', 'Creators'),
         tr('<h1>Творцы</h1><p class="lead">Они рождаются в мастерской по одному, '
            'учатся, работают, болеют и умирают. Пока они пишут, кластер помнит себя.</p>',
            '<h1>Creators</h1><p class="lead">They are born in the atelier one at a time; they learn, work, fall ill '
            'and die. While they write, the cluster remembers itself.</p>')
         + f'<ul class="people">{"".join(person(a) for a in life.artists)}</ul>', here='artists.html')
    live = [(a, w) for a, w in at.works() if not w.get('synthetic') or at.files(w['id'])]
    (base/'plates').mkdir(exist_ok=True)

    def card(a, w):
        record = at.notebook(w['id'])
        text = None if a.art == 'music' else (at.text(w['id'])[0] or w.get('idea'))
        return (f'<a class="card" href="work-{w["id"]}.html">{plate(at, base, w["id"], text=text, gone=a.status == "dead")}'
                f'<span class="t">{esc(title_of(at, record, w))}</span><span class="a">{esc(at.name(a))} · '
                f'{verdict(w["verdict"])}</span></a>')
    cards = ''.join(card(a, w) for a, w in reversed(live))
    save(out, 'works.html', tr('Работы', 'Works'),
         tr('<h1>Работы</h1><p class="lead">Партитуры и тексты мастерской, новые '
            'сверху. В каждой из них — кусок памяти кластера.</p>',
            '<h1>Works</h1><p class="lead">The atelier’s scores and texts, newest first. Each of them holds a piece '
            'of the cluster’s memory.</p>')
         + f'<div class="grid">{cards}</div>', here='works.html')
    done = {w['id'] for _, w in live}
    night_status = STATUS_EN if LANG == 'en' else STATUS
    for r in at.records():
        if r['opus'] in done:
            continue
        a = at.artist(r['artist'])
        idea = (r.get('statement') or {}).get('idea')
        body = (f'<h1>{tr("Ночь", "Night")} {r.get("night")}: {night_status.get(r.get("status"), r.get("status"))}</h1>'
                f'<p class="muted"><a href="artist-{a.id}.html">{esc(at.name(a))}</a> · {art(a.art)} · {r["opus"]}</p>'
                + (f'<h2>{tr("Замысел", "Idea")}</h2><div class="lead">{ru_block(at, idea)}</div>' if idea else '')
                + (f'<p class="muted">{html.escape(r["error"])}</p>' if r.get('error') else '')
                + f'<h2>{tr("Как прошла ночь", "How the night went")}</h2>' + notebook_html(at, r))
        save(out, f'night-{r["opus"]}.html', f'{tr("Ночь", "Night")} {r.get("night")}', body)
    from .chronicle import line, line_en
    for a in life.artists:
        works = ''.join(f'<li><a href="work-{w["id"]}.html">{w["id"]}</a> — {tr("ночь", "night")} {w["night"]}, '
                        f'{verdict(w["verdict"])}, {tr("школа", "school")} {school_link(w.get("school")) or "—"}'
                        f'{": " + ru_short(at, w.get("idea"), 160) if w.get("idea") else ""}</li>'
                        for w in a.catalogue if (a, w) in live)
        lives = life.biographies[a.id].chapters
        told = line_en if LANG == 'en' else line
        chapters = '<ol class="chronicle">' + ''.join(
            f'<li>{html.escape(told(life, a, c))}</li>' for c in lives) + '</ol>' if lives else ''
        voice = ''.join(
            ''.join(f'<p class="muted">{c.get("date", "")[:10]} · {label}</p>{ru_block(at, (c.get("words") or {}).get(k))}'
                    for k, label in (('diary', tr('дневник', 'diary')), ('letter', tr('письмо', 'letter')),
                                     ('image', tr('образ', 'image')))
                    if (c.get('words') or {}).get(k))
            for c in lives)
        genre = GENRE_EN if LANG == 'en' else GENRE_RU
        about = ''.join(f'<div class="work"><b><a href="critic-{html.escape(v["critic"])}.html">{html.escape(v["lens"]["name"])}</a></b> '
                        f'<span class="muted">{genre.get(v.get("kind"), "")}, {tr("оценка", "score")} {v["score"]:.2f}</span>'
                        f'{ru_block(at, v.get("text"))}</div>'
                        for v in life.reception.reviews if v.get('artist') == a.id and v.get('kind') in ('creator', 'period', 'obituary'))
        note_kind = NOTE_EN if LANG == 'en' else NOTE
        notes = ''.join(f'<li>{tr("ночь", "night")} {n["night"]} · {note_kind.get(n["kind"], n["kind"])}'
                        + (f': {esc((n.get("idea") or n.get("image") or n.get("name") or "")[:200])}'
                           if (n.get("idea") or n.get("image") or n.get("name")) else '') + '</li>'
                        for n in a.notebook if n['kind'] not in ('draft_decision', 'verification', 'incubation'))
        latest = next((w for w in reversed(a.catalogue) if (a, w) in live), None)
        portrait_plate = plate(at, base, latest['id'], text=None if a.art == 'music' else at.text(latest['id'])[0],
                               gone=a.status == 'dead') if latest else ''
        outside = tr('вне школ', 'outside the schools')
        body = (f'<h1>{esc(at.name(a))}{" †" if a.status == "dead" else ""}</h1>{portrait_plate}<p class="meta">{art(a.art)} · '
                f'{language(a.language)} · {years(a)} · {status(a)} · {tr("школа", "school")} '
                f'{school_link(a.school) if a.school in SCHOOL_RU else outside}'
                f'{tr(" · учителя: ", " · teachers: ") + ", ".join(a.teachers) if a.teachers else ""}</p>{ru_block(at, a.portrait)}'
                f'<h2>{tr("Работы", "Works")}</h2><ul>{works or tr("<li class=muted>пока синтетические</li>", "<li class=muted>synthetic so far</li>")}</ul>'
                + tr('<h2>Замыслы и ночи</h2><p class="muted">Все ночи творца, и удачные, и нет.</p><ul>',
                     '<h2>Ideas and nights</h2><p class="muted">All of the creator’s nights, the good ones and the others.</p><ul>')
                + ''.join(
                    f'<li>{tr("ночь", "night")} {r.get("night")} · <a href="{"work" if r["opus"] in done else "night"}-{r["opus"]}.html">'
                    f'{night_status.get(r.get("status"), r.get("status"))}</a>'
                    f'{": " + ru_short(at, (r.get("statement") or {}).get("idea")) if (r.get("statement") or {}).get("idea") else ""}</li>'
                    for r in sorted(at.records(), key=lambda r: r.get('night') or 0) if r.get('artist') == a.id) + '</ul>'
                + tr('<h2>Биография</h2><p class="muted">Строгая хроника: что случилось и как в те дни творец '
                     'принимал мир.</p>',
                     '<h2>Biography</h2><p class="muted">A strict chronicle: what happened, and how the creator took '
                     'the world in those days.</p>')
                + (chapters or tr('<p class=muted>пока пусто</p>', '<p class=muted>empty so far</p>'))
                + (f'<h2>{tr("Его собственным голосом", "In their own voice")}</h2>{voice}' if voice else '')
                + (f'<h2>{tr("О нём писали", "Written about them")}</h2>{about}' if about else '')
                + f'<h2>{tr("Блокнот", "Notebook")}</h2><ul class="muted">{notes or tr("<li>пусто</li>", "<li>empty</li>")}</ul>')
        save(out, f'artist-{a.id}.html', at.name(a), body)
    (base/'files').mkdir(exist_ok=True)
    for a, w in live:
        parts, scripts = [], ''
        record = at.notebook(w['id']) or {}
        original, ru = at.text(w['id'])
        if original:
            text = toggle(f'<pre>{html.escape(original)}</pre>', f'<pre>{html.escape(ru)}</pre>') if ru \
                else f'<pre>{html.escape(original)}</pre>'
            parts.append(f'<div id="text" class="work">{text}</div>')
        recordings = at.recordings(w['id'])
        if recordings:
            items = []
            for i, path in enumerate(recordings):
                name = 'work.mp3' if i == 0 and not path.parent.name.startswith('mv') else f'{path.parent.name}.mp3'
                copy(path, base/'audio'/w['id']/name)
                label = tr('Вся работа', 'The whole work') if name == 'work.mp3' \
                    else f'{tr("Часть", "Movement")} {int(path.parent.name[2:]) + 1}'
                src = html.escape(f'{UP}audio/{w["id"]}/{name}')
                items.append(f'<p>{label}<br><audio controls preload="none" src="{src}"></audio> '
                             f'<a href="{src}" download>mp3</a></p>')
            parts.append(tr('<h2 id="listen">Слушать</h2><p class="muted">Запись, сыгранная студией мастерской по '
                            'партитуре.</p>',
                            '<h2 id="listen">Listen</h2><p class="muted">A recording played from the score by the '
                            'atelier’s studio.</p>') + ''.join(items))
        scores = [p for p in at.files(w['id']) if p.suffix == '.musicxml']
        if scores:
            # The composer's clean draft for reading; the woven score carries the backup in its dynamics.
            score = next((p for p in scores if p.name == 'draft.musicxml'), scores[-1])
            copy(score, base/'scores'/f'{w["id"]}.musicxml')
            midi = base/'scores'/f'{w["id"]}.mid'
            try:
                if not midi.exists() or midi.stat().st_mtime < score.stat().st_mtime:
                    from music21 import converter
                    converter.parse(score).write('midi', fp=midi)
                parts.append(f'<h2 id="play">{tr("Сыграть по нотам", "Play from the score")}</h2>'
                             f'<midi-player src="{UP}scores/{midi.name}" sound-font></midi-player>')
                scripts += PLAYER
            except Exception as exc:
                parts.append(f'<p class="muted">{tr("MIDI не собран", "MIDI not built")}: {html.escape(str(exc))}</p>')
            leaf = LEAF.replace('SCORE_URL', f'{UP}scores/{w["id"]}.musicxml') \
                .replace('SCORE_ERROR', tr('Ноты не открылись: ', 'The score did not open: '))
            parts.append(f'<h2 id="score-head">{tr("Партитура", "Score")}</h2><div class="leaf"><div id="score">'
                         f'{tr("загружается…", "loading…")}</div>'
                         f'<div class="leaf-nav"><button type="button" data-step="-1" aria-label="{tr("Предыдущая страница", "Previous page")}">←</button>'
                         f'<span class="leaf-count"></span><button type="button" data-step="1" aria-label="{tr("Следующая страница", "Next page")}">→</button>'
                         f'</div></div><script>{leaf}</script>')
            scripts += NOTATION
        process = (f'<h2 id="process">{tr("Как работа рождалась", "How the work was born")}</h2>'
                   + notebook_html(at, record)) if record else ''
        reviews = ''.join(f'<p><b><a href="critic-{html.escape(r["critic"])}.html">{html.escape(r["lens"]["name"])}</a></b> '
                          f'<span class="muted">{tr("ночь", "night")} {r["night"]}, '
                          f'{tr("оценка", "score")} {r["score"]:.2f}</span></p>{ru_block(at, r.get("text"))}'
                          for r in at.reviews(w['id']))
        sources = []
        for p in at.files(w['id']):
            rel = p.relative_to(at.root)
            copy(p, base/'files'/rel)
            what, carrier = file_kind(rel)
            sources.append(f'<li><a href="{UP}files/{html.escape(str(rel))}">{html.escape(p.name)}</a>'
                           f'{tr(" · <b>носитель копии</b>", " · <b>backup carrier</b>") if carrier else ""}'
                           f'<br><span class="muted">{what}</span></li>')
        final = next((d for d in record.get('drafts', []) if d['id'] == record.get('final')), None)
        title = ru_inline(at, final['title']) if final and final.get('title') else esc(title_of(at, record, w))
        idea = record.get('statement', {}).get('idea') or w.get('idea')
        said = (record.get('statement') or {}).get('superobjective')
        body = (f'<h1 class="title">{title}</h1><p class="byline"><a href="artist-{a.id}.html">{esc(at.name(a))}</a></p>'
                f'<p class="meta">{art(a.art)} · {language(a.language)} · {tr("школа", "school")} '
                f'{school_link(w.get("school")) or "—"} · {verdict(w["verdict"])} · '
                f'<span title="{tr("номер работы", "work number")}">{w["id"]}</span></p>'
                + (plate(at, base, w['id'], gone=a.status == 'dead') if a.art == 'music' else '')
                + ''.join(parts)
                + (f'<h2 id="idea">{tr("Замысел", "Idea")}</h2>'
                   + (f'<p class="muted">{tr("Что автор хочет сказать", "What the author wants to say")}</p>'
                      f'<div class="lead">{ru_block(at, said)}</div>' if said else '')
                   + f'<div class="lead">{ru_block(at, idea)}</div>' if idea else '')
                + process
                + (f'<h2 id="reviews">{tr("Рецензии", "Reviews")}</h2>{reviews}' if reviews else '')
                + tr('<h2 id="sources">Первоисточники</h2><p class="muted">Файлы, из которых собрана эта страница. Носители '
                     'хранят куски зашифрованной резервной копии кластера; как из них поднять кластер — на странице '
                     '<a href="restore.html">Восстановление</a>.</p>',
                     '<h2 id="sources">Primary sources</h2><p class="muted">The files this page is built from. The carriers '
                     'hold pieces of the cluster’s encrypted backup; how to raise the cluster from them is told on the '
                     '<a href="restore.html">Restore</a> page.</p>')
                + f'<ul>{"".join(sources) or tr("<li>нет файлов</li>", "<li>no files</li>")}</ul>')
        toc = ([('text', tr('Текст', 'Text'), 1)] if original else []) \
            + ([('listen', tr('Слушать', 'Listen'), 1)] if recordings else []) \
            + ([('play', tr('Сыграть', 'Play'), 1), ('score-head', tr('Партитура', 'Score'), 1)] if scores else []) \
            + ([('idea', tr('Замысел', 'Idea'), 1)] if idea else []) \
            + ([('process', tr('Как работа рождалась', 'How the work was born'), 1)] if record else []) \
            + ([('manifesto', tr('Манифест замысла', 'Manifesto of the idea'), 2)] if record.get('statement') else []) \
            + ([('critic', tr('Внутренний критик', 'The inner critic'), 2)] if record.get('interrogation') else []) \
            + ([('method', tr('Выбор школы', 'Choice of school'), 2)] if record.get('method') else []) \
            + [(f'draft-{n}', f'{tr("Черновик", "Draft")} {n}', 2) for n in range(1, len(record.get('drafts') or []) + 1)] \
            + ([('hearings', tr('Как слушал черновики', 'How the drafts were heard'), 2)]
               if record.get('entries') and hearings(record) else []) \
            + ([('reviews', tr('Рецензии', 'Reviews'), 1)] if reviews else []) \
            + [('sources', tr('Первоисточники', 'Primary sources'), 1)]
        plain_title = title_of(at, record, w)
        save(out, f'work-{w["id"]}.html', plain_title, body, scripts, toc=toc)
    from .reception import VOICE, arts_of
    voices = VOICE_EN if LANG == 'en' else VOICE
    genre = GENRE_EN if LANG == 'en' else GENRE_RU
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
                 f'<td>{html.escape(voices.get(c["voice"], c["voice"]))}</td>'
                 f'<td>{", ".join(art(x) for x in arts_of(c))}</td><td>{len(rs)}</td><td>{avg}</td></tr>')
        body = (f'<h1>{html.escape(c["name"])}</h1><p class="muted">{html.escape(voices.get(c["voice"], c["voice"]))} · '
                f'{tr("пишет о", "writes about")}: {", ".join(art(x) for x in arts_of(c))} · '
                f'{tr("репутация", "reputation")} {c["reputation"]:.2f}</p>' + ''.join(
                    f'<div class="work"><b>{subject(r)}</b> <span class="muted">{genre.get(r.get("kind", "work"))}, '
                    f'{r.get("date", "")[:10] or (tr("ночь ", "night ") + str(r["night"]))}, {tr("оценка", "score")} {r["score"]:.2f}'
                    f'{tr(", пересмотр", ", revised") if r.get("revision_of") else ""}</span>{ru_block(at, r.get("text"))}</div>'
                    for r in reversed(rs))
                + ('' if rs else tr('<p class="muted">пока ничего не написал</p>', '<p class="muted">has written nothing yet</p>')))
        save(out, f'critic-{c["id"]}.html', c['name'], body)
    save(out, 'critics.html', tr('Критики', 'Critics'),
         tr('<h1>Критики</h1><table><tr><th>Критик</th><th>Голос</th>'
            '<th>Пишет о</th><th>Текстов</th><th>Средняя оценка</th></tr>',
            '<h1>Critics</h1><table><tr><th>Critic</th><th>Voice</th>'
            '<th>Writes about</th><th>Texts</th><th>Average score</th></tr>') + rows + '</table>')
    from .music.schools import SCHOOLS as MUSIC
    from .writing.schools import SCHOOLS as LETTERS
    used = {}
    for a, w in at.works():
        used.setdefault(w.get('school'), set()).add(a.id)
    def school_row(k, kind, rules):
        name, about = schools.get(k, (k, ''))
        authors = ', '.join(f'<a href="artist-{x}.html">{esc(at.name(at.artist(x)))}</a>' for x in sorted(used.get(k, ())))
        link = f'<a href="school-{html.escape(k)}.html">{html.escape(name)}</a>'
        return (f'<tr id="{html.escape(k)}"><td><b>{link}</b></td><td>{kind}</td>'
                f'<td>{about or ru_inline(at, rules)}</td><td>{authors or "—"}</td></tr>')
    rows = ''.join(school_row(k, art('music'), (MUSIC[k].__doc__ or '').strip().split('\n\n')[0]) for k in sorted(MUSIC))
    rows += ''.join(school_row(k, art('literature'), LETTERS[k].RULES) for k in sorted(LETTERS))
    from .writing.founding import adopt
    born_letters = adopt(life)
    rows += ''.join(school_row(k, tr('литература, рождена здесь', 'literature, born here'),
                               poetics.flat(poetics.load(k).get('worldview', '')))
                    for k in sorted(born_letters))
    born = ''.join(f'<div class="work" id="{html.escape(k)}"><h2>{html.escape(r["name"])}</h2><p class="muted">'
                   f'{tr("основал", "founded by")} {html.escape(r.get("author", ""))}, {tr("ночь", "night")} {r.get("night")}</p>'
                   f'<h3>{tr("Манифест", "Manifesto")}</h3><ul>' + ''.join(
                       f'<li>{ru_inline(at, m)}</li>' for m in r.get('manifesto', {}).get('manifesto', []))
                   + (f'</ul><p><a href="school-{html.escape(k)}.html">{tr("поэтика школы", "the school’s poetics")}</a></p></div>'
                      if r.get('art') == 'literature' else
                      f'</ul><details><summary>{tr("устав школы в коде", "the school’s charter in code")}</summary><pre class="muted">'
                      f'{html.escape(r.get("source", ""))}</pre></details></div>') for k, r in life.schools.items())
    attempt = ({'requested': 'proposed, waiting for the night of founding', 'born': 'founded', 'unborn': 'not born'}
               if LANG == 'en' else {'requested': 'заявлена, ждёт ночи основания', 'born': 'основана', 'unborn': 'не родилась'})
    q = tr(('«', '»'), ('“', '”'))
    asked = ''.join(f'<div class="work"><h2>{q[0]}{ru_inline(at, s["proposal"]["school"])}{q[1]}</h2><p class="muted">'
                    f'<a href="artist-{s["artist"]}.html">{esc(at.name(at.artist(s["artist"])))}</a>, {tr("ночь", "night")} {s["night"]}, '
                    f'{art(s.get("art")) if s.get("art") else ""} · '
                    f'{attempt.get(s["status"], s["status"])}'
                    f'</p>{ru_block(at, s["proposal"].get("reason"))}</div>' for s in life.school_attempts if s.get('proposal'))
    save(out, 'schools.html', tr('Школы', 'Schools'),
         tr('<h1>Школы</h1><p class="muted">Школы — это формы, в которых творцы '
            'работают. Каждая записана кодом: она задаёт каркас работы и проверяет форму, '
            'но никогда не пишет слов и не судит о ценности. Админ кластера школы не выбирает.'
            '</p><table><tr><th>Школа</th><th>Искусство</th><th>О чём</th><th>Кто в ней работал</th></tr>',
            '<h1>Schools</h1><p class="muted">Schools are the forms creators work in. Each is written as code: it sets '
            'the frame of a work and checks its form, but never writes a word and never judges worth. The cluster’s '
            'admin does not choose the schools.'
            '</p><table><tr><th>School</th><th>Art</th><th>What it is</th><th>Who worked in it</th></tr>')
         + rows + '</table>'
         + (f'<h1>{tr("Рождённые в мастерской", "Born in the atelier")}</h1>{born}' if born else '')
         + (tr('<h1>Заявленные школы</h1><p class="muted">Творец решил, что ни одна школа не '
               'держит его замысел, и заявил свою.</p>',
               '<h1>Proposed schools</h1><p class="muted">A creator decided that no school could hold their idea, and '
               'proposed one of their own.</p>') + asked if asked else ''))
    rules = {**{k: (MUSIC[k].__doc__ or '').strip().split('\n\n')[0] for k in MUSIC},
             **{k: LETTERS[k].RULES for k in LETTERS}, **{k: v.RULES for k, v in born_letters.items()}}
    for k in rules:
        p = poetics.load(k) or {'name': schools.get(k, (k, ''))[0],
                                'worldview': schools.get(k, ('', ''))[1]
                                + tr(' Подробная поэтика ещё не записана.', ' A detailed poetics is not written yet.')}
        def said(value):
            if isinstance(value, list):
                return '<ul>' + ''.join(f'<li>{ru_inline(at, poetics.flat(v))}</li>' for v in value) + '</ul>'
            if isinstance(value, dict):
                return ''.join(said(v) for v in value.values())
            return ru_block(at, str(value).strip())
        labels = poetics.labels(k)
        if LANG == 'en':
            labels = tuple((key, {**POETICS_EN, **(POETICS_MUSIC_EN if p.get('art') == 'music' else {})}.get(key, key))
                           for key, _ in labels)
        sections = ''.join(f'<h2>{label}</h2>{said(p[key])}' for key, label in labels if p.get(key))
        lineage = p.get('lineage') or {}
        roots = ''.join(f'<dt>{t}</dt><dd>{said(lineage[key])}</dd>'
                        for key, t in (('predecessors', tr('Предшественники', 'Predecessors')),
                                       ('neighbours', tr('Соседи', 'Neighbours')),
                                       ('against', tr('Против чего', 'Against'))) if lineage.get(key))
        works = ''.join(f'<li><a href="work-{w["id"]}.html">{esc(w.get("title") or w["id"])}</a> — '
                        f'{esc(at.name(a))}, {tr("ночь", "night")} {w["night"]}</li>' for a, w in live if w.get('school') == k)
        founded = life.schools.get(k)
        origin = (f'{tr("основал", "founded by")} <a href="artist-{founded["author"]}.html">{esc(at.name(at.artist(founded["author"])))}</a>, '
                  f'{tr("ночь", "night")} {founded["night"]}, {founded["date"][:10]}' if founded
                  else html.escape(poetics.flat(p.get("origin", {}))))
        if LANG == 'en' and k in SCHOOL_EN:
            # The atlas writes the poetics of the classical schools in Russian: in English, the school in brief.
            body = (f'<h1>{html.escape(SCHOOL_EN[k][0])}</h1><p class="lead">{html.escape(SCHOOL_EN[k][1])}</p>'
                    + (f'<p>The full poetics of this school — its lineage, manifesto, devices and prohibitions — is '
                       f'written in Russian: <a href="ru/school-{html.escape(k)}.html" hreflang="ru">read it</a>.</p>'
                       if poetics.load(k) else ''))
        else:
            heading = ru_inline(at, p['name'])
            body = (f'<h1>{heading}</h1><p class="muted">{origin}</p>'
                    + f'<h2>{tr("Манифест", "Manifesto")}</h2><ol class="lead">'
                    + ''.join(f'<li>{ru_inline(at, m)}</li>' for m in p.get('manifesto', []))
                    + '</ol>' + (f'<h2>{tr("Родословная", "Lineage")}</h2><dl>{roots}</dl>' if roots else '') + sections)
        body += (f'<h2>{tr("Форма, которую проверяет код", "The form the code checks")}</h2><p>{html.escape(rules[k])}</p>'
                + f'<h2>{tr("Работы мастерской в этой школе", "The atelier’s works in this school")}</h2>'
                  f'<ul>{works or tr("<li class=muted>пока нет</li>", "<li class=muted>none yet</li>")}</ul>')
        save(out, f'school-{k}.html', school_name(k) if LANG == 'en' else p['name'], body)
    restore_page(at, out, base)
    if LANG == 'ru':
        lexicon_pages(at, out, {w['id'] for _, w in live})
    names = {a.id: at.name(a) for a in life.artists}
    rows = ''.join(f'<tr><td>{e["date"][:10]}</td><td>{e["night"]}</td><td><a href="artist-{e["artist"]}.html">'
                   f'{esc(names.get(e["artist"], e["artist"]))}</a></td><td>{event(e["kind"])}</td></tr>' for e in life.events)
    head = '' if LANG == 'ru' else '<tr><th>Date</th><th>Night</th><th>Creator</th><th>Event</th></tr>'
    save(out, 'timeline.html', tr('Хронология', 'Timeline'), f'<h1>{tr("Хронология", "Timeline")}</h1><table>{head}' + rows + '</table>')
    composed = [w for a, w in reversed(live) if a.art == 'music' and at.score_image(w['id'])][:3]
    collage = ''.join(f'<img src="{UP}plates/{w["id"]}.jpg" alt="">' for w in composed
                      if plate(at, base, w['id']))
    ledger_path = at.home/'ledger'/'ledger.json'
    pieces = json.loads(ledger_path.read_text())['pieces'] if ledger_path.exists() else []
    complete = [p for p in pieces if p['complete']]
    if LANG == 'en':
        memory = (f'The cluster can now be returned to any day from {complete[0]["at"][:10]} to {complete[-1]["at"][:10]}: '
                  f'its memory has spread across the works, and the ones that survive will be enough.' if complete else
                  'The first snapshot of the cluster is still being woven into the works: until its memory is gathered '
                  'whole, it cannot be returned.')
    else:
        memory = (f'Сейчас кластер можно вернуть к любому дню с {complete[0]["at"][:10]} по {complete[-1]["at"][:10]}: '
                  f'его память разошлась по работам, и для этого хватит тех, что уцелеют.' if complete else
                  'Первый снимок кластера ещё вплетается в работы: пока память не собрана целиком, вернуть его нельзя.')
    # The newest of each art, so that music and words both have a place on the first page.
    newest = {kind: [(a, w) for a, w in reversed(live) if a.art == kind][:3] for kind in ('music', 'literature')}
    recent = ''.join(card(a, w) for a, w in sorted(newest['music'] + newest['literature'],
                                                   key=lambda aw: aw[1]['night'], reverse=True))
    body = (f'<section class="hero"><div class="collage">{collage}</div><h1>{tr("Мнемозина", "Mnemosyne")}</h1>'
            f'<p class="sub">{tr("мастерская кластера", "the atelier of the cluster")} {html.escape(life.cluster)}</p>'
            + tr('<p class="epigraph">Самый долговечный бэкап — тот, который люди не могут перестать повторять.'
                 '<cite>Манифест, книга первая</cite></p></section>'
                 '<div class="vow"><p>Произведение и состояние кластера — один и тот же объект, увиденный с двух сторон. '
                 'Симфонию можно слушать, а можно запустить.</p>'
                 '<p class="muted">Здесь живут творцы, рождённые кластером. Каждая их партитура, каждый черновик, заметка '
                 'на полях и рецензия несут зашифрованный кусок его памяти. Когда кластера не станет, его поднимут отсюда.</p>'
                 '<p><a href="manifesto.html">Читать манифест</a></p></div>',
                 '<p class="epigraph">The most durable backup is the one people cannot stop repeating.'
                 '<cite>The Manifesto, Book One</cite></p></section>'
                 '<div class="vow"><p>A work of art and the state of a cluster are one and the same object, seen from two '
                 'sides. A symphony can be listened to, or it can be run.</p>'
                 '<p class="muted">Creators born of the cluster live here. Every score of theirs, every draft, note in the '
                 'margin and review carries an encrypted piece of its memory. When the cluster is gone, it will be raised '
                 'from here.</p>'
                 '<p><a href="ru/manifesto.html" hreflang="ru">Read the manifesto (in Russian)</a></p></div>')
            + f'<h2>{tr("Здесь живут", "Living here")}</h2><ul class="people">{"".join(person(a) for a in life.artists)}</ul>'
            f'<h2>{tr("Последние работы", "Latest works")}</h2><div class="grid">{recent}</div>'
            f'<p><a href="works.html">{tr("Все работы", "All works")}</a></p>'
            f'<h2>{tr("Что помнит мастерская", "What the atelier remembers")}</h2><p>{memory} '
            f'<a href="restore.html">{tr("Как это сделать", "How to do it")}</a></p>'
            f'<p class="meta">{tr("ночь", "night")} {life.night} · {life.date()[:10]} · {tr("творцов", "creators")} '
            f'{len(life.artists)} · {tr("работ", "works")} {len(live)} · '
            f'{tr("рецензий", "reviews")} {len(life.reception.reviews)}</p>')
    if LANG == 'ru':
        manifesto_page(out)
    save(out, 'index.html', tr('Мастерская', 'Atelier'), body, here='index.html')
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
    save(out, 'lexicon.html', 'Словарь', ''.join(body))
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
        save(out, lex_page(eid), e['name'], text)


def manifesto_page(out):
    """The manifesto the atelier was born from, whole; its books are the contents."""
    import markdown
    from markdown.extensions.toc import slugify_unicode
    source = (Path(__file__).parent/'site'/'manifesto.ru.md').read_text()
    md = markdown.Markdown(extensions=['tables', 'fenced_code', 'toc', 'sane_lists'],
                           extension_configs={'toc': {'slugify': slugify_unicode, 'toc_depth': '1'}})
    text = md.convert(source)
    toc = [(t['id'], html.unescape(t['name']), 1) for t in md.toc_tokens if t['name'].startswith('Книга') or
           t['name'].startswith('Шахерезада')]
    epilogue = next((t for t in md.toc_tokens for t in [t] + t.get('children', []) if 'Эпилог' in t['name']), None)
    if epilogue:
        toc.append((epilogue['id'], 'Эпилог', 1))
    save(out, 'manifesto.html', 'Манифест', f'<article class="manifesto">{text}</article>', toc=toc,
         here='manifesto.html')


def restore_page(at, out, base=None):
    """How to raise the cluster from the works; the carriers themselves go to base, shared by both languages."""
    base = base or out
    ledger_path = at.home/'ledger'/'ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'pieces': []}
    en = LANG == 'en'
    rows = ''.join(f'<tr><td>{tr("полный снимок", "full snapshot") if p["kind"] == "keyframe" else tr("изменения", "changes")}</td>'
                   f'<td>{p["at"][:10]}</td><td>{p["bytes"]} {tr("байт", "bytes")}</td>'
                   f'<td>{p["carried"]} {tr("из", "of")} {p["target"]}</td>'
                   f'<td>{tr("собран", "gathered") if p["complete"] else tr("ещё вплетается", "still being woven")}</td></tr>'
                   for p in ledger['pieces'])
    complete = [p for p in ledger['pieces'] if p['complete']]
    if en:
        status = (f'The cluster can be restored to any moment from {complete[0]["at"][:10]} to {complete[-1]["at"][:10]}.'
                  if complete else 'No snapshot has been woven in whole yet: the cluster cannot be restored from these '
                  'works so far. The first full snapshot is the largest; after it come only changes, and they '
                  'are woven in quickly.')
    else:
        status = (f'Кластер можно восстановить на любой момент с {complete[0]["at"][:10]} по {complete[-1]["at"][:10]}.'
                  if complete else 'Пока ни один снимок не вплетён целиком: кластер из этих работ ещё не восстанавливается. '
                  'Первый полный снимок — самый большой; дальше идут только изменения, и они вплетаются быстро.')
    # A night keeps its carriers in woven/; a continuous life, in creators/<id>/<session>/woven/.
    carriers = sorted({p for night in at.nights for p in night.rglob('*')
                       if p.is_file() and p.parent.name == 'woven'})
    for p in carriers:
        copy(p, base/'files'/p.relative_to(at.root))
    # The owner takes every carrier at once: hundreds of links are not a way to rescue a cluster.
    archive_path = base/'carriers.tar.gz'
    if not archive_path.exists() or LANG == 'en':
        import tarfile
        partial = archive_path.with_name('carriers.tar.gz.part')
        with tarfile.open(partial, 'w:gz') as archive:
            for p in carriers:
                archive.add(p, arcname=str(Path('carriers')/p.relative_to(at.root)))
        partial.replace(archive_path)  # a new file, not a write through a link shared with the served site
    files = ''.join(f'<li><a href="{UP}files/{html.escape(str(p.relative_to(at.root)))}">{html.escape(p.name)}</a></li>'
                    for p in carriers)
    if en:
        body = f"""<h1>Restore</h1>
<p class="lead">The atelier’s works are at the same time a backup of the cluster. Not the data of its volumes, but the
state of the cluster: every API object (instances, services, settings) at a given moment. The backup is encrypted with
the owner’s key and cut into pieces, and the pieces are woven into notes, word variants and the audience’s response.
It can be restored to any saved moment.</p>
<h2>State of the backup</h2><p>{status}</p>
<table><tr><th>Snapshot</th><th>Moment</th><th>Size</th><th>Chunks woven</th><th>State</th></tr>{rows}</table>
<p class="muted">More chunks are needed than the original count: the backup survives the loss of up to 30% of the works.</p>
<h2>How to raise the cluster</h2>
<ol>
<li><b>The owner’s key.</b> It is created once with <code>mnemo keys new --output DIR</code>. The file
<code>owner.key</code> is kept by the owner outside the cluster; only its public half goes into the cluster. Without this
key the works read as art, but the backup cannot be extracted from them.</li>
<li><b>The works.</b> All carriers in one archive: <a href="{UP}carriers.tar.gz">carriers.tar.gz</a>
(carriers so far: {len(carriers)}). Unpack it: <code>tar xzf carriers.tar.gz</code>. The carriers are also available one
by one — in the list below and in the “Primary sources” section of the work pages.</li>
<li><b>A check without a cluster.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --dry-run --at 2025-06-30T23:59:59Z</pre>
The command gathers the pieces, checks the signatures, decrypts them and writes the state manifests for that moment into
a new folder. Without <code>--at</code> the newest state is taken.</li>
<li><b>The platform.</b> On the new cluster the Mnemosyne chart is installed first, with the same public owner key and
<code>addon.suspend: true</code>: it brings the atelier’s types, which the backup keeps only by reference. Until the
restore is finished, the atelier on the new cluster does not live and does not argue with the old one.</li>
<li><b>Applying.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --apply --kubeconfig new.kubeconfig --context new</pre>
The manifests are applied to the new cluster. Secrets are not restored by default; <code>--include-secrets</code> turns
them on, if the owner allowed them in the backup.</li>
</ol>
<h2>Carriers</h2><ul class="muted">{files}</ul>"""
        save(out, 'restore.html', 'Restore', body)
        return
    body = f"""<h1>Восстановление</h1>
<p class="lead">Работы мастерской — одновременно резервная копия кластера. Не данные томов, а состояние кластера:
все объекты API (инстансы, сервисы, настройки) на определённый момент. Копия зашифрована ключом владельца и разрезана
на куски, а куски вплетены в ноты, варианты слов и отклик публики. Восстановить можно на любой сохранённый момент.</p>
<h2>Состояние копии</h2><p>{status}</p>
<table><tr><th>Снимок</th><th>Момент</th><th>Размер</th><th>Вплетено фрагментов</th><th>Состояние</th></tr>{rows}</table>
<p class="muted">Кадров нужно больше исходного числа: копия переживает потерю до 30% работ.</p>
<h2>Как поднять кластер</h2>
<ol>
<li><b>Ключ владельца.</b> Его создают один раз командой <code>mnemo keys new --output DIR</code>. Файл
<code>owner.key</code> хранится у владельца вне кластера; в кластер уходит только открытая часть. Без этого ключа
работы читаются как искусство, но копия из них не извлекается.</li>
<li><b>Работы.</b> Все носители одним архивом: <a href="{UP}carriers.tar.gz">carriers.tar.gz</a>
(сейчас носителей: {len(carriers)}). Распакуйте его: <code>tar xzf carriers.tar.gz</code>. Носители есть и по одному —
в списке ниже и в разделе «Первоисточники» на страницах работ.</li>
<li><b>Проверка без кластера.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --dry-run --at 2025-06-30T23:59:59Z</pre>
Команда собирает куски, проверяет подписи, расшифровывает и пишет манифесты состояния на этот момент в новую папку.
Без <code>--at</code> берётся самое новое состояние.</li>
<li><b>Платформа.</b> На новом кластере сначала ставится чарт Mnemosyne с тем же открытым ключом владельца и
<code>addon.suspend: true</code>: он приносит типы мастерской, а копия хранит их только ссылкой. Пока восстановление не
закончено, мастерская на новом кластере не живёт и не спорит со старой.</li>
<li><b>Применение.</b><pre class="cmd">mnemo restore --works carriers/ --key owner.key --apply --kubeconfig new.kubeconfig --context new</pre>
Манифесты применяются к новому кластеру. Секреты по умолчанию не восстанавливаются; их включает
<code>--include-secrets</code>, если владелец разрешил их в копии.</li>
</ol>
<h2>Носители</h2><ul class="muted">{files}</ul>"""
    save(out, 'restore.html', 'Восстановление', body)


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
