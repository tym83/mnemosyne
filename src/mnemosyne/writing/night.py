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
import re
from typing import Literal

from pydantic import BaseModel

from .. import artist as ideas
from ..climate import feel, temperament
from ..literature import DRAFTING, LANGUAGE, Writer
from ..mood import words
from ..weave.variants import plain
from . import translator
from .schools import SCHOOLS


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


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=1))


class WriterNight:
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
        drafting = DRAFTING.set(True)
        spoken = LANGUAGE.set(LANGUAGE_NAMES.get(self.artist.language))
        try:
            return self._run(inner, drafts)
        except Exception as exc:
            self.record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            LANGUAGE.reset(spoken)
            DRAFTING.reset(drafting)
            self.save()

    def _run(self, inner, drafts):
        a, life = self.artist, self.life
        sensed = feel(life.climate, a.sensitivity or temperament(a.id))
        inner = words(sensed, False, False) + '\n' + inner
        names = {b.id: ('творец' if b.name == b.id else b.name) for b in life.artists}
        teachers = [names.get(t, t) for t in a.teachers]
        if not a.portrait or a.portrait == '[portrait awaiting words]':
            p = ideas.self_portrait({'born': a.birth, 'age_days': a.age, 'teachers': teachers, 'art': 'литература',
                                     'catalogue': [w.get('idea') for w in a.catalogue if w.get('idea')]},
                                    self.entries, backend=self.backend, inner=inner)
            a.name, a.portrait = p.name, plain(p.portrait)
            self.record['portrait'] = p.model_dump()
        system = (f'Ты писатель {a.name}. {a.portrait}\nУчителя: {teachers}. '
                  'Художественные решения принимаешь ты. Не упоминай инфраструктуру.')
        portrait = ideas.SelfPortrait(name=a.name, portrait=a.portrait, what_i_am_as_artist=a.portrait,
                                      wounds=[], loves=[], fears=[], inner_critic={**a.inner_critic, 'teachers': teachers})
        st, history = ideas.statement(portrait, 'литература',
            [json.dumps({k: w.get(k) for k in ('idea', 'school', 'verdict')}, ensure_ascii=False) for w in a.catalogue],
            self.entries, backend=self.backend,
            contemporaries=[str(w['idea']) for b in life.artists if b.id != a.id for w in b.catalogue if w.get('idea')],
            illumination=life.idea_seed(a.id), inner=inner, set_aside=a.problem,
            encounters=life.encounters(a.id))
        self.record.update(statement=st.model_dump(), interrogation=history)
        last = history[-1]['interrogation']
        if not ideas.accepted(last['verdict']):
            life.set_aside_idea(a.id, st.idea, last.get('reasons', ''))
            self.record['status'] = 'idea_rejected'
            return self.record
        a.problem = None
        schools = {k: {'kind': m.KIND, 'rules': m.RULES} for k, m in SCHOOLS.items()}
        method = self.ask(system, json.dumps({'idea': st.model_dump(), 'schools': schools,
            'task': 'Choose the school that serves the idea, or invent_school (a future night will found it).'},
            ensure_ascii=False), Method, 'method')
        self.record['method'] = method.model_dump()
        if method.kind == 'invent_school' or method.school not in SCHOOLS:
            life.school_attempts.append({'artist': a.id, 'night': life.night, 'status': 'requested',
                                         'art': 'literature', 'proposal': method.model_dump()})
            self.record['status'] = 'school_requested'
            return self.record
        school = SCHOOLS[method.school]
        rng = random.Random(int.from_bytes(hashlib.sha256(self.work_id.encode()).digest()[:8]))
        plan = {**deepcopy(school.EXAMPLE_PLAN), 'seed': rng.randrange(2**31), 'title': ''}
        frame = school.skeleton(plan, rng)
        self.record.update(plan=plan, frame=frame)
        corrections, final, reading = [], None, None
        for n in range(drafts):
            draft = self.write(system, st, school, method.school, frame, corrections, n)
            reading = self.ask(ideas.taste_prompt(a.inner_critic) + 'Прочитай черновик как его автор: держится ли '
                               'замысел, живой ли язык, не повтор ли это. accept, rewrite или repetition.',
                               json.dumps({'idea': st.idea, 'school': method.school, 'text': plain(draft['text'])},
                                          ensure_ascii=False), Reading, f'read:{n}')
            draft['reading'] = reading.model_dump()
            final = draft
            if reading.verdict == 'accept':
                break
            corrections = reading.corrections
        observation = {'feature': features(final['text']), 'quality': max(0., min(1., reading.quality)),
                       'verdict': reading.verdict, 'idea': st.idea,
                       'novelty': self.novelty(features(final['text'])),
                       'process': {'school': method.school, 'drafts': len(self.record['drafts'])}}
        work = life.record_work(a.id, observation)
        work['school'] = method.school
        self.record.update(final=final['id'], verdict=reading.model_dump(),
                           status='accepted' if reading.verdict == 'accept' else 'unfinished')
        self.record['translation'] = translator.translate(final['text'], a.language, self.entries,
                                                          backend=self.backend, step='translate:work')
        (self.root/f'{self.work_id}.txt').write_text(plain(final['text']))
        if self.record['translation']:
            (self.root/f'{self.work_id}.ru.txt').write_text(self.record['translation'])
        if reading.matters:
            life.event(a, 'writer_work', work=work['id'], verdict=reading.verdict)
            chapter = self.ask('Ты летописец мастерской. Пиши Жизнеописания об искусстве.',
                               json.dumps({'artist': a.name, 'idea': st.idea, 'school': method.school,
                                           'verdict': reading.model_dump()}, ensure_ascii=False), Chapter, 'lives-chapter')
            life.biographies[a.id].chapters[-1]['text'] = chapter.text
        return self.record

    def write(self, system, st, school, name, frame, corrections, n):
        problems = []
        for attempt in range(3):
            draft = self.ask(system, json.dumps({'idea': st.model_dump(), 'school': name, 'rules': school.RULES,
                'frame': frame, 'corrections': corrections, 'form_problems': problems,
                'task': 'Write the complete work in text, in your mother tongue, within the frame.'},
                ensure_ascii=False), Draft, f'draft:{n}:{attempt}')
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
