"""A writer's night: idea, inner critic, school, drafts held to their form, verdict, the work.

The same shape as a composer's night, in words. The writer drafts in their
mother tongue with their own variants; the school's frame and mechanical form
check keep the form; the inner critic reads and decides; the Translator
renders the result into Russian. The work, its drafts and the notebook are
carriers: which variant remains is decided when the night is woven.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import threading
import re
from typing import Literal

from pydantic import BaseModel

from .. import artist as ideas
from ..literature import LANGUAGE, Writer
from ..weave.variants import plain
from . import founding, poetics, translator


class Method(BaseModel):
    kind: Literal['school', 'invent_school']
    school: str
    reason: str


class Draft(BaseModel):
    title: str
    text: str
    diary: str


class Reading(BaseModel):
    verdict: Literal['accept', 'rewrite', 'repetition']
    reasons: str
    corrections: list[str]
    matters: bool
    quality: float


class Chapter(BaseModel):
    text: str


def features(text):
    """Four descriptive numbers for novelty against the writer's own catalogue."""
    reading = plain(text)
    tokens = re.findall(r'\w+', reading.lower())
    lines = [l for l in reading.splitlines() if l.strip()]
    sentences = max(1, len(re.findall(r'[.!?…]+', reading)))
    return [min(1., len(tokens) / 3000), len(set(tokens)) / max(1, len(tokens)),
            min(1., len(tokens) / sentences / 40), min(1., len(lines) / max(1, len(tokens)) * 8)]


def library(life, a):
    """The schools this writer knows: their own, their teachers', what they met around them, what they read.

    Nobody knows every school. The library grows with age, and its order is the
    writer's own, so no school is first for everyone.
    """
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:library'.encode()).digest()[:8]))
    known = [w.get('school') for w in a.catalogue]
    for t in a.teachers:
        teacher = next((b for b in life.artists if b.id == t), None)
        known += [w.get('school') for w in (teacher.catalogue if teacher else [])]
    tonight = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:{life.night}'.encode()).digest()[:8]))
    recent = [w.get('school') for b in life.artists if b.id != a.id and b.art == a.art
              for w in b.catalogue if life.night - w.get('night', 0) <= 120]
    known += tonight.sample(recent, min(3, len(recent)))
    SCHOOLS = founding.schools(life)
    reading = sorted(k for k in SCHOOLS if not k.startswith('born-'))
    r.shuffle(reading)
    known += reading[:3 + a.age // 60]
    # Schools born here are talked about: a writer hears of one or two of them.
    born = sorted(k for k in SCHOOLS if k.startswith('born-'))
    known += tonight.sample(born, min(2, len(born)))
    seen = []
    for k in known:
        if k in SCHOOLS and k not in seen:
            seen.append(k)
    tonight.shuffle(seen)
    return seen


def tradition(a):
    """How this writer stands to schools: by temperament, not by an administrator's preference."""
    if a.openness > .65:
        return 'Ты ищешь своё и не любишь ходить чужими дорогами; тебе тесно в том, что уже стало привычным.'
    if a.openness < .35:
        return 'Ты держишься традиции и школы учителя; новизна ради новизны тебе чужда.'
    return 'Ты открыт и чужим школам, и своей традиции, без суеты.'


def around(life, a):
    """What the writer's contemporaries have been writing lately: a fashion to follow, ignore or flee."""
    from collections import Counter
    SCHOOLS = founding.schools(life)
    recent = Counter(w.get('school') for b in life.artists if b.art == a.art
                     for w in b.catalogue if not w.get('synthetic') and life.night - w.get('night', 0) <= 120
                     and w.get('school') in SCHOOLS)
    total = sum(recent.values())
    if total < 3:
        return ''
    names = {k: (poetics.load(k) or {}).get('name', k) for k in recent}
    return 'Что сейчас пишут вокруг тебя: ' + ', '.join(
        f'{names[k]} — {n} из {total}' for k, n in recent.most_common(4)) + '.'


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1))


class WriterNight:
    # Several writers may work on one night; the shared life is changed by one at a time.
    LIFE = threading.RLock()

    def __init__(self, life, artist_id, root, *, backend=None):
        self.life = life
        self.artist = next(a for a in life.artists if a.id == artist_id)
        if self.artist.art != 'literature':
            raise ValueError("a writer's night needs a writer")
        if self.artist.status not in ('working', 'ill'):
            raise ValueError('a living working artist is required')
        self.work_id = f'{artist_id}-w{len(self.artist.catalogue):05d}'
        self.root, self.backend = Path(root), backend
        self.root.mkdir(parents=True, exist_ok=False)
        self.entries = []
        self.writer = Writer(self.entries, backend=backend, data_class='art')
        self.record = {'version': 1, 'art': 'literature', 'artist': artist_id, 'opus': self.work_id,
                       'night': life.night, 'language': self.artist.language, 'status': 'searching',
                       'entries': self.entries, 'drafts': []}

    def save(self):
        dump(self.root/'notebook.json', self.record)

    def ask(self, system, prompt, schema, step, **kw):
        try:
            return self.writer.ask(system, prompt, schema, step, **kw)
        finally:
            self.save()

    def run(self, inner='', *, drafts=3):
        from ..lineage import LANGUAGE_NAMES
        spoken = LANGUAGE.set(LANGUAGE_NAMES.get(self.artist.language))
        try:
            return self._run(inner, drafts)
        except Exception as exc:
            self.record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            LANGUAGE.reset(spoken)
            self.save()

    def _run(self, inner, drafts):
        a, life = self.artist, self.life
        from ..psyche import inner as inner_weather, remembered
        own = remembered(life, a)
        inner = '\n'.join(x for x in (inner_weather(life, a), own, inner) if x)
        names = {b.id: ('творец' if b.name == b.id else b.name) for b in life.artists}
        teachers = [names.get(t, t) for t in a.teachers]
        if not a.portrait or a.portrait == '[portrait awaiting words]':
            p = ideas.self_portrait({'born': a.birth, 'age_days': a.age, 'teachers': teachers, 'art': 'литература',
                                     'catalogue': [w.get('idea') for w in a.catalogue if w.get('idea')]},
                                    self.entries, backend=self.backend, inner=inner)
            a.name, a.portrait = p.name, plain(p.portrait)
            self.record['portrait'] = p.model_dump()
        SCHOOLS = founding.schools(life)
        home = next((w['school'] for w in reversed(a.catalogue) if w.get('school') in SCHOOLS), None)
        system = (f'Ты писатель {a.name}. {a.portrait}\nТвои учителя: {", ".join(teachers) or "нет"}. '
                  'Художественные решения принимаешь ты. Не упоминай технику, компьютеры, серверы.')
        portrait = ideas.SelfPortrait(name=a.name, portrait=a.portrait, what_i_am_as_artist=a.portrait,
                                      wounds=[], loves=[], fears=[], inner_critic={**a.inner_critic, 'teachers': teachers})
        if home:
            inner += ('\n\nТвоя школа — ' + poetics.brief(home, SCHOOLS[home].RULES) +
                      '\nЗамысел может родиться внутри её поэтики, в споре с ней или вне её.')
        st, history = ideas.statement(portrait, 'литература',
            [json.dumps({k: w.get(k) for k in ('idea', 'school', 'verdict')}, ensure_ascii=False) for w in a.catalogue],
            self.entries, backend=self.backend,
            contemporaries=[str(w['idea']) for b in life.artists if b.id != a.id for w in b.catalogue if w.get('idea')],
            illumination=life.idea_seed(a.id), inner=inner, set_aside=a.problem,
            encounters=life.encounters(a.id))
        self.record.update(statement=st.model_dump(), interrogation=history)
        last = history[-1]['interrogation']
        if not ideas.accepted(last['verdict']):
            with self.LIFE:
                life.set_aside_idea(a.id, st.idea, last.get('reasons', ''))
            self.record['status'] = 'idea_rejected'
            return self.record
        a.problem = None
        idea = self.idea_words(st)
        known = library(life, a)
        choices = '\n\n'.join(f'{k} — {poetics.brief(k, SCHOOLS[k].RULES)}' for k in known)
        method = self.ask(system, f'{idea}\n\nШколы, которые ты знаешь:\n\n{choices}\n\n{tradition(a)}\n'
                          f'{around(life, a)}\n\n'
                          'Выбери школу, чья поэтика — картина мира, время, голос, язык — служит этому замыслу, '
                          'а не только её форму. В school напиши её код (слово перед тире). Если ни одна школа '
                          'не держит замысел, выбери invent_school и в school назови школу, которую хочешь '
                          'основать: ты напишешь её поэтику и манифест, твой внутренний критик проверит, не '
                          'повторяет ли она известную, и этой же ночью ты напишешь в ней первую вещь.',
                          Method, 'method')
        self.record['method'] = method.model_dump()
        if method.kind == 'invent_school' or method.school not in SCHOOLS:
            self.system = system
            record, history = founding.found(self, idea, method, SCHOOLS)
            self.record['school_birth'] = {'proposal': method.model_dump(), 'attempts': history}
            with self.LIFE:
                if record is None:
                    life.school_unborn(a.id, method.school, history)
                    self.record['status'] = 'school_unborn'
                    return self.record
                life.found_school(a.id, record)
            SCHOOLS = founding.schools(life)
            method = Method(kind='school', school=record['id'], reason=method.reason)
            self.record['method'] = {**method.model_dump(), 'founded': record['name']}
        school = SCHOOLS[method.school]
        rng = random.Random(int.from_bytes(hashlib.sha256(self.work_id.encode()).digest()[:8]))
        plan = {**deepcopy(school.EXAMPLE_PLAN), 'seed': rng.randrange(2**31), 'title': ''}
        frame = school.skeleton(plan, rng)
        self.record.update(plan=plan, frame=frame)
        reader = poetics.full(method.school, school.RULES, keys=['forbidden', 'markers', 'reading'])
        corrections, final, reading = [], None, None
        for n in range(drafts):
            draft = self.write(system, idea, school, method.school, frame, corrections, n)
            reading = self.ask(ideas.taste_prompt(a.inner_critic) +
                               'Ты перечитываешь свой черновик дважды: как его автор и как читатель этой школы.\n'
                               + reader + '\n\nДержится ли замысел? Есть ли в тексте живое: человек, вещь, '
                               'мгновение, событие, — а не тезис? Понятно ли и интересно ли это по меркам этой '
                               'школы (тёмное допустимо, если школа его требует, но текст должен держать)? Живой ли '
                               'язык? Не повтор ли это? accept, rewrite или repetition; в corrections — что '
                               'конкретно переписать.',
                               f'{idea}\n\nЧерновик:\n\n{plain(draft["text"])}', Reading, f'read:{n}')
            draft['reading'] = reading.model_dump()
            final = draft
            if reading.verdict == 'accept':
                break
            corrections = reading.corrections
        observation = {'feature': features(final['text']), 'quality': max(0., min(1., reading.quality)),
                       'verdict': reading.verdict, 'idea': st.idea,
                       'novelty': self.novelty(features(final['text'])),
                       'process': {'school': method.school, 'drafts': len(self.record['drafts'])}}
        with self.LIFE:
            work = life.record_work(a.id, observation)
        work.update(school=method.school, title=plain(final['title']), excerpt=plain(final['text'])[:900],
                    diary=plain(final.get('diary') or '')[:400])
        self.record.update(final=final['id'], verdict=reading.model_dump(),
                           status='accepted' if reading.verdict == 'accept' else 'unfinished')
        self.record['translation'] = translator.translate(final['text'], a.language, self.entries,
                                                          backend=self.backend, step='translate:work')
        work.update(text=plain(final['text']), translation=self.record['translation'])
        (self.root/f'{self.work_id}.txt').write_text(plain(final['text']))
        if self.record['translation']:
            (self.root/f'{self.work_id}.ru.txt').write_text(self.record['translation'])
        if reading.matters:
            with self.LIFE:
                life.event(a, 'writer_work', work=work['id'], verdict=reading.verdict)
        return self.record

    @staticmethod
    def idea_words(st):
        """The accepted idea as the writer would say it, not as a form to fill."""
        parts = [f'Замысел: {st.idea}', f'Сверхзадача: {st.superobjective}', f'Мысль: {st.thought}',
                 'Чувства: ' + '; '.join(st.emotions), 'Чего я боюсь: ' + '; '.join(st.risks)]
        return '\n'.join(plain(p) for p in parts)

    def write(self, system, idea, school, name, frame, corrections, n):
        problems = []
        body = poetics.full(name, school.RULES)
        for attempt in range(3):
            prompt = (f'{idea}\n\nТы пишешь в поэтике этой школы:\n{body}\n\n'
                      f'Каркас этой работы (его проверяет код): {json.dumps(frame, ensure_ascii=False)}\n'
                      + (f'\nЧто ты решил переписать после прошлого черновика:\n- ' + '\n- '.join(corrections) + '\n'
                         if corrections else '')
                      + (f'\nФорма не удержана: {"; ".join(problems)}\n' if problems else '')
                      + '\nНапиши произведение целиком, на родном языке. История и живое в ней важнее всего; '
                        'пиши для читателя, а не для отчёта о замысле. В diary — пара строк в дневник о том, '
                        'что решилось в этом черновике.')
            draft = self.ask(system, prompt, Draft, f'draft:{n}:{attempt}')
            problems = school.check(plain(draft.text), frame, self.artist.language)
            if not problems:
                break
        record = {'id': f'{self.work_id}-draft-{n:02d}', 'title': draft.title, 'text': draft.text,
                  'diary': draft.diary, 'form_problems': problems}
        self.record['drafts'].append(record)
        return record

    def novelty(self, feature):
        own = [w['feature'] for w in self.artist.catalogue if not w.get('synthetic') and w.get('feature')]
        if not own:
            return 1.
        return max(0., min(1., min(sum(abs(x - y) for x, y in zip(feature, f)) / 2 for f in own)))
