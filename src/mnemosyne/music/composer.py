"""An idea-led night. Writer stays with the notebook; music runs in a studio pod.

No rejected idea becomes a finished work. Insufficient carrier capacity leaves
an explicit pending snapshot, never a claim that the archive was recovered.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import os
import random
import shlex
from pathlib import Path
import subprocess
import tarfile
import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
from .. import artist as ideas
from ..atelier import Atelier, obj
from ..lineage import Lineage
from ..literature import Writer
from ..weave.variants import plain
from ..climate import tendencies, year_shape, feel, temperament
from ..mood import words


class Method(BaseModel):
    kind: Literal['school', 'notagen', 'cross', 'broken_principle', 'invent_school']
    school: str
    sources: list[str]
    principle: str
    transformation: str
    concept: str
    reason: str
    notagen_prompt: str  # period|composer|instrumentation, or empty
    form: Literal['school', 'symphony']


class PlanText(BaseModel):
    # JSON text keeps the Writer's strict outer schema compatible with the
    # different versioned grammars. The parsed document is validated below.
    plan_json: str
    diary: str


class Listening(BaseModel):
    verdict: Literal['accept', 'rewrite', 'repetition']
    reasons: str
    corrections: list[str]
    matters: bool
    quality: float = Field(ge=0, le=1)


class Chapter(BaseModel):
    text: str


class PlanRejected(ValueError):
    """The artist has not supplied a realizable plan; no worker should run."""


def dump(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def example_plan(school):
    from .schools import SCHOOLS
    path = Path(__file__).parent/'schools/plans'/f'{school}.json'
    return json.loads(path.read_text()) if path.exists() else deepcopy(SCHOOLS[school].__plan__)


def validate_plan(plan, method, *, sketch=False):
    from .schools import SCHOOLS
    if method.kind == 'invent_school':
        raise NotImplementedError('school birth requires a reviewed grammar and decoder')
    if method.form == 'symphony':
        from .symphony import validate
        validate(plan, study=sketch)
        used = {name for mv in plan['movements'] for sec in mv['sections']
                for name in sec.get('schools', mv.get('schools', []))}
        if method.kind == 'cross' and (len(set(method.sources)) < 2 or not set(method.sources) <= used):
            raise ValueError('a cross must realize at least two declared source schools')
        if method.kind == 'broken_principle' and (not method.principle or not method.transformation):
            raise ValueError('name the broken principle and its concrete transformation')
        return plan
    from .schools.plan import SchoolPlan
    if method.school not in SCHOOLS or plan.get('school') != method.school:
        raise ValueError('plan must name the chosen existing school')
    if type(plan.get('seed')) is not int or not plan.get('title'):
        raise ValueError('integer seed and title required')
    SchoolPlan.model_validate(plan)
    from .schools.common import validate
    validate(plan)
    if plan.get('audio_profile') == 'native_sfz':
        from .instrumentarium import audio_ensemble
        audio_ensemble(plan.get('orchestration', plan['ensemble']))
    if method.kind in ('cross', 'broken_principle'):
        raise ValueError('crosses and broken principles use a symphony plan with explicit material development')
    return plan


def plan_contract(method):
    from .schools import SCHOOLS
    from .instrumentarium import audio_contract
    if method.form == 'symphony':
        from .symphony import FORMS, TRANSFORMS, ORCHESTRA
        return {'version': 1, 'forms': FORMS, 'transforms': sorted(TRANSFORMS),
                'audio': audio_contract(), 'required_orchestra': ORCHESTRA,
                'orchestra_rule': 'This grammar writes fixed instrument-bound lines; retain at least all required orchestra slots.',
                'contract': 'symphony.validate: 3–5 movements, 20–45 minutes (sketch study may be shorter)',
                'example': json.loads((Path(__file__).parent/'plans/symphony-test.json').read_text())}
    if method.school not in SCHOOLS:
        raise ValueError('unknown school')
    from .schools.plan import SchoolPlan
    from .school_birth import source_of
    return {'schema': SchoolPlan.model_json_schema(), 'audio': audio_contract(), 'contract': 'schools.common.validate; durations in seconds; sounding MIDI; '
                        'sum(form.duration)=duration; duration*tempo/60 on sixteenth grid; '
                        'each section >=4 quarters; register overlaps every instrument by an octave',
            'example': example_plan(method.school),
            'grammar': source_of(method.school)}


class Studio:
    """Fixed namespace/node boundary. Isolated source and run directory per night."""
    def __init__(self, root: Path, pod='studio-0'):
        if pod not in ('studio-0', 'studio-1'):
            raise ValueError('only studio-0/ws1 and studio-1/ws4 are allowed')
        self.root, self.pod = root, pod
        self.remote = '/work/composer/' + uuid4().hex
        self.kube = ['kubectl', '--kubeconfig', str(Path('~/workshop.txt').expanduser()),
                     '--context', 'admin@workshop', '-n', 'tenant-scheherazade']

    def call(self, args, **kwargs):
        return subprocess.run(self.kube + args, check=True, **kwargs)

    def setup(self):
        data = json.loads(self.call(['get', 'pod', self.pod, '-o', 'json'],
                                   capture_output=True, text=True).stdout)
        expected = {'studio-0': 'ws1', 'studio-1': 'ws4'}[self.pod]
        if data['spec'].get('nodeName') != expected:
            raise RuntimeError('studio is on an unauthorized node')
        self.call(['exec', self.pod, '--', 'mkdir', '-p', self.remote + '/src'])
        self.call(['cp', str(Path(__file__).resolve().parents[1]),
                   self.pod + ':' + self.remote + '/src/scheherazade'])
        self.call(['exec', self.pod, '--', 'ln', '-s', 'scheherazade',
                   self.remote + '/src/mnemosyne'])

    def wait(self, remote, timeout=14400, every=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(every)
            try:
                done = self.call(['exec', self.pod, '--', 'cat', remote + '/exit'],
                                 capture_output=True, text=True)
            except subprocess.CalledProcessError:
                continue  # not finished yet, or the link dropped
            if done.stdout.strip():
                return int(done.stdout)
        raise TimeoutError(f'composer worker did not finish in {timeout} s')

    def fetch(self, remote, name, destination, tries=20):
        """Bring notation, mp3 and metadata home; lossless FLAC stays in the studio."""
        archive = shlex.quote(name + '.tgz')
        pack = (f'cd {shlex.quote(remote)} && tar -czf {archive} --exclude=.drafts '
                f"--exclude='*.wav' --exclude='*.f32' --exclude='*.flac' {shlex.quote(name)} && sha256sum {archive}")
        local = destination/(name + '.tgz')
        for attempt in range(tries):
            try:
                if attempt == 0 or not digest:
                    digest = self.call(['exec', self.pod, '--', 'sh', '-c', pack],
                                       capture_output=True, text=True).stdout.split()[0]
                with local.open('wb') as out:
                    self.call(['exec', self.pod, '--', 'cat', remote + '/' + name + '.tgz'], stdout=out)
                if hashlib.sha256(local.read_bytes()).hexdigest() == digest:
                    break
            except (subprocess.CalledProcessError, IndexError):
                digest = None
            time.sleep(10)
        else:
            raise RuntimeError(f'could not fetch {name} from the studio after {tries} tries')
        with tarfile.open(local) as tar:
            tar.extractall(destination, filter='data')
        local.unlink()

    def run(self, request, destination):
        destination.mkdir(parents=True, exist_ok=False)
        dump(destination/'request.json', request)
        remote = self.remote + '/' + destination.name
        self.call(['exec', self.pod, '--', 'mkdir', '-p', remote])
        self.call(['cp', str(destination/'request.json'), self.pod + ':' + remote + '/request.json'])
        worker = ['nice', '-n', '19', 'env',
                  'PYTHONPATH=' + self.remote + '/src:/work/lineage-check/deps',
                  'OMP_NUM_THREADS=1', 'OPENBLAS_NUM_THREADS=1',
                  *[k + '=' + os.environ[k] for k in ('MNEMOSYNE_NOTAGEN', 'NOTAGEN_DIR',
                      'NOTAGEN_WEIGHTS', 'NOTAGEN_DEVICE') if k in os.environ],
                  '/work/venv/bin/python', '-m', 'mnemosyne.music.composer_worker',
                  remote + '/request.json', '--out', remote + '/result']
        # The worker runs detached in the pod: a long exec stream from the
        # laptop does not survive a flaky link, short polls do.
        inner = shlex.join(worker) + ' >studio.log 2>&1; echo $? >exit'
        self.call(['exec', self.pod, '--', 'sh', '-c',
                   f'cd {shlex.quote(remote)} && nohup sh -c {shlex.quote(inner)} </dev/null >/dev/null 2>&1 &'])
        error = None
        try:
            code = self.wait(remote)
            if code != 0:
                error = RuntimeError(f'composer worker exited with {code}')
        except Exception as exc:
            error = exc
        # Fetch failed attempts too; never delete the remote notebook.
        for name in ('studio.log', 'result'):
            try:
                self.fetch(remote, name, destination)
            except Exception:
                if error is None:
                    raise
        if error:
            raise error
        result = json.loads((destination/'result/result.json').read_text())
        result['remote'] = {'pod': self.pod, 'directory': remote + '/result'}
        return result


def feature_vector(summary):
    """Fixed measurable descriptors; these are not an aesthetic quality score."""
    density = summary.get('density', [])
    return [min(1., (summary.get('bpm') or 60)/240),
            min(1., (sum(density)/max(1, len(density)))/100),
            min(1., summary.get('parts', 1)/32), float(summary.get('reprise', 0))]


def art_sketch(sketch):
    return {k: sketch[k] for k in ('plan', 'analysis', 'form') if k in sketch}


class Night:
    def __init__(self, life, artist_id, root, studio, *, backend=None, sound=True,
                 cluster_state=None, ledger_root=None):
        self.life = life
        self.artist = next(a for a in life.artists if a.id == artist_id)
        if self.artist.art != 'music':
            raise ValueError('a composer night needs a composer')
        if self.artist.status not in ('working', 'ill'):
            raise ValueError('a living working artist is required')
        self.work_id = f'{artist_id}-w{len(self.artist.catalogue):05d}'
        self.root, self.studio, self.backend = Path(root), studio, backend
        # Sound is a side branch: the backup lives in scores and the process;
        # a work may be rendered here, played by people, or left on paper.
        self.sound = sound
        # Observed cluster objects for tonight's backup, and the atelier's shared ledger.
        self.cluster_state, self.ledger_root = cluster_state, ledger_root
        from .school_birth import register_all
        register_all(life.schools)
        self.root.mkdir(parents=True, exist_ok=False)
        studio_record = {'pod': getattr(studio, 'pod', None), 'remote': getattr(studio, 'remote', None)}
        self.entries, self.sketches = [], []
        self.record = {'version': 1, 'artist': artist_id, 'opus': self.work_id,
                       'night': life.night, 'chronicle': life.cluster+'-lives',
                       'studio': studio_record, 'status': 'searching', 'entries': self.entries,
                       'sketches': self.sketches}
        self.writer = Writer(self.entries, backend=backend, data_class="art")
        self.work = None
        self.save()

    def save(self):
        atelier = Atelier(self.life.cluster, self.root/'atelier')
        for sk in self.sketches:
            sk['file_refs'] = [atelier.store.put(self.root/p) for p in sk.get('files', [])]
        if self.work is not None:
            self.work['process']['composer'] = deepcopy(self.record)
        dump(self.root/'notebook.json', self.record)
        dump(self.root/'lineage.json', self.life.state())
        atelier.lineage(self.life)
        # Pending/failed nights are ordinary state too, before _work is called.
        if self.work is None:
            atelier.objects.extend([
                obj('Opus', self.work_id, {'artist': self.artist.id, 'art': 'music',
                    'notebook': self.work_id+'-notebook', 'phase': self.record['status']}),
                obj('Notebook', self.work_id+'-notebook', deepcopy(self.record))])
        else:
            for o in atelier.objects:
                if o['kind'] == 'Notebook' and o['metadata']['name'] == self.work['notebook']:
                    o['spec']['composer'] = deepcopy(self.record)
        for sk in self.sketches:
            files = [atelier.store.put(self.root/p) for p in sk.get('files', [])]
            if sk['id'] == self.record.get('final'):
                for o in atelier.objects:
                    if o['kind'] == 'Opus' and o['metadata']['name'] == self.work_id:
                        o['spec'].update(files=files, art='music', final_sketch=sk['id'])
            if not any(o['kind'] == 'Sketch' and o['metadata']['name'] == sk['id'] for o in atelier.objects):
                atelier.objects.append(obj('Sketch', sk['id'], {**sk, 'artist': self.artist.id,
                    'opus': self.work_id, 'notebook': self.work_id+'-notebook', 'files': files}))
        atelier.write()
        self.objects = atelier.objects

    def ask(self, system, prompt, schema, step, **kwargs):
        try:
            return self.writer.ask(system, prompt, schema, step, **kwargs)
        finally:
            self.save()

    def plan(self, method, context, step, *, sketch=False):
        contract = plan_contract(method)
        prompt = json.dumps({'task': 'Write the complete plan as JSON text in plan_json. '
                    'Choose every musical parameter yourself; no cluster facts. '
                    + ('Short study of the method.' if sketch else 'Complete work, derived from the sketches.'),
                    'context': context, 'contract': contract}, ensure_ascii=False)
        for attempt in range(3):
            answer = self.ask(self.system, prompt, PlanText, f'{step}:{attempt}',
                              images=[self.root/p for p in context.get('candidate_images', [])])
            try:
                plan = validate_plan(json.loads(answer.plan_json), method, sketch=sketch)
                if method.kind == 'notagen':
                    materials = [c.get('material') for c in context['notagen_candidates']['candidates']
                                 if c.get('material')]
                    if plan.get('notagen_material') not in materials:
                        raise ValueError('use one archived candidate material verbatim as notagen_material')
                    if not any('notagen' in sec.get('schools', mv.get('schools', []))
                               for mv in plan['movements'] for sec in mv['sections']):
                        raise ValueError('NotaGen material must actually participate in the work')
                self.entries.append({'step': step, 'plan': plan, 'diary': answer.diary})
                self.save()
                return plan
            except (ValueError, TypeError, KeyError) as exc:
                self.entries.append({'step': step, 'invalid_plan': answer.plan_json, 'error': str(exc)})
                self.save()
                prompt += '\nCorrect the plan without discarding the idea: ' + str(exc)
        raise PlanRejected('artist plan failed validation three times; retained for revision')

    def studio_run(self, request, label):
        try:
            return self.studio.run(request, self.root/label)
        except Exception as exc:
            folder = self.root/label
            logs = {str(p.relative_to(self.root)): p.read_text(errors='replace')
                    for p in folder.rglob('*.log') if p.is_file()}
            self.entries.append({'step': label, 'request': request, 'error': str(exc), 'worker_logs': logs})
            self.save()
            raise

    def found_school(self, st, method):
        """Manifesto, grammar as code, trial, inner critic. Returns the new school id or None."""
        from . import school_birth
        a = self.artist
        manifesto = self.ask(self.system, json.dumps({'idea': st.model_dump(), 'method': method.model_dump(),
            'task': 'You are founding a new school. Write its manifesto: name, philosophy, techniques, what it '
                    'forbids, what it rejects and argues with, which existing schools it breaks with. choice=invent.'},
            ensure_ascii=False), ideas.Method, 'school-manifesto')
        critic = (ideas.taste_prompt(a.inner_critic) + 'Суди новую школу: не переименование ли это известной '
                  '(назови её), держится ли её философия, воплощают ли правила манифест, плодотворна ли она. '
                  'Замер отличия от существующих школ приложен. Реши: accept или rewrite.')
        record, history = school_birth.found(manifesto.model_dump(), self.ask, self.system, critic,
            born_plans={k: v['plan'] for k, v in self.life.schools.items() if v.get('status') == 'accepted'})
        self.record['school_birth'] = {'manifesto': manifesto.model_dump(), 'attempts': history}
        if record is None:
            self.life.school_unborn(a.id, manifesto.name, history)
            self.record['status'] = 'school_unborn'
            self.save()
            return None
        self.life.found_school(a.id, record)
        school_birth.register(record['id'], record['source'], record['plan'])
        self.save()
        return record['id']

    def born_sources(self):
        return {k: {'source': v['source'], 'plan': v['plan']} for k, v in self.life.schools.items()
                if v.get('status') == 'accepted'}

    def music(self, plan, method, label):
        result = self.studio_run({'action': 'compose', 'plan': plan, 'form': method.form,
                                  'born_schools': self.born_sources()}, label)
        folder = self.root/label/'result'
        files = [str(p.relative_to(self.root)) for p in sorted(folder.rglob('*'))
                 if p.is_file() and '.drafts' not in p.parts]
        sk = {'id': self.work_id+'-'+label, 'stage': label, 'plan': plan,
              'analysis': result['analysis'], 'files': files,
              'score': str((folder/result['score']).relative_to(self.root)),
              'form': method.form,
              'carriers': [{**c, 'score': str((folder/c['score']).relative_to(self.root))}
                           for c in result.get('carriers', [])],
              'images': [str((folder/p).relative_to(self.root)) for p in result['images']]}
        self.sketches.append(sk)
        self.save()
        return sk

    def run(self, inner, *, drafts=3, key=None):
        from ..literature import DRAFTING, LANGUAGE
        from ..lineage import LANGUAGE_NAMES
        token = DRAFTING.set(True)
        spoken = LANGUAGE.set(LANGUAGE_NAMES.get(self.artist.language))
        try:
            return self._run(inner, drafts=drafts, key=key)
        finally:
            LANGUAGE.reset(spoken)
            DRAFTING.reset(token)

    def _run(self, inner, *, drafts=3, key=None):
        a = self.artist
        sensed = feel(self.life.climate, a.sensitivity or temperament(a.id))
        inner = words(sensed, False, False) + '\n' + inner
        name = 'художник' if a.name == a.id else a.name
        names = {b.id: ('художник' if b.name == b.id else b.name) for b in self.life.artists}
        teachers = [names.get(t, t) for t in a.teachers]
        self.system = (f'Ты композитор {name}. {a.portrait}\nУчителя: {teachers}. '
                       'Художественные решения принимаешь ты. Не упоминай инфраструктуру. '
                       'Слушай через анализ и изображения партитуры; это не непосредственное прослушивание.')
        try:
            if not a.portrait or a.portrait == '[portrait awaiting words]':
                portrait = ideas.self_portrait({'born': a.birth, 'age_days': a.age,
                    'teachers': teachers, 'catalogue': [w.get('idea') for w in a.catalogue if w.get('idea')]},
                    self.entries, backend=self.backend, inner=inner)
                a.name, a.portrait = portrait.name, plain(portrait.portrait)
                name = a.name
                self.system = (f'Ты композитор {a.name}. {a.portrait}. Учителя: {teachers}. '
                               'Не упоминай инфраструктуру. Принимай художественные решения по идее, '
                               'анализу звучания и изображениям партитуры.')
                self.record['portrait'] = portrait.model_dump()
                self.save()
            portrait = ideas.SelfPortrait(name=name, portrait=a.portrait + '\nУчителя: '+', '.join(teachers),
                what_i_am_as_artist=a.portrait, wounds=[], loves=[], fears=[], inner_critic={**a.inner_critic, 'teachers': teachers})
            st, history = ideas.statement(portrait, 'музыка',
                [json.dumps({k: w.get(k) for k in ('idea', 'method', 'verdict')}, ensure_ascii=False)
                 for w in a.catalogue], self.entries, backend=self.backend,
                contemporaries=[str(w['idea']) for b in self.life.artists if b.id != a.id
                                for w in b.catalogue if w.get('idea')],
                illumination=self.life.idea_seed(a.id), inner=inner, set_aside=a.problem,
                encounters=self.life.encounters(a.id))
            self.record.update(statement=st.model_dump(), interrogation=history)
            last = history[-1]['interrogation']
            if not ideas.accepted(last['verdict']):
                self.life.set_aside_idea(a.id, st.idea, last.get('reasons', ''))
                self.record['status'] = 'idea_rejected'
                self.save()
                return self.record
            a.problem = None
            self.save()
            from .schools.catalog import LISTEN
            from .instrumentarium import audio_contract
            born = {k: {'name': v['name'], 'author': v['author'], 'manifesto': v['manifesto'].get('manifesto', [])}
                    for k, v in self.life.schools.items() if v.get('status') == 'accepted'}
            method = self.ask(self.system, json.dumps({'audio': audio_contract(), 'notagen_available': os.environ.get('MNEMOSYNE_NOTAGEN') == 'self-hosted', 'idea': st.model_dump(), 'schools': LISTEN,
                'schools_born_here': born,
                'task': 'Choose school (a founding school or one born here), NotaGen period style, cross, broken principle, '
                'or invent_school. For a cross or broken principle choose form=symphony and name the exact development. '
                'invent_school: you then write the manifesto and the grammar of a new school yourself; '
                'it must pass a trial and your inner critic before you compose in it.'}, ensure_ascii=False),
                Method, 'method')
            self.record['method'] = method.model_dump()
            if method.kind == 'invent_school':
                school = self.found_school(st, method)
                if school is None:
                    return self.record
                method.kind, method.school, method.form = 'school', school, 'school'
                self.record['method'] = method.model_dump()
            shades = ideas.halftones(portrait, st, method.concept, inner, self.entries, backend=self.backend)
            self.record['halftones'] = shades.model_dump()
            rng = random.Random(int.from_bytes(hashlib.sha256(self.work_id.encode()).digest()[:8]))
            structural = tendencies(sensed, a.inner_critic, method.model_dump(), rng)
            context = {'statement': st.model_dump(), 'method': method.model_dump(), 'halftones': shades.model_dump(),
                       'structural_tendencies': structural,
                       'structure_instruction': 'These sampled tendencies are weighted suggestions, not fixed mappings. '
                           'Interpret through the idea and chosen method; retain your reasons in the diary.'}
            occasion = next((o for o in self.life.occasions if o['moment'] <= self.life.night), None)
            if occasion:
                context['occasion'] = {k: occasion[k] for k in ('genre', 'moment')}
            if method.form == 'symphony' and self.life.climate_history:
                context['year_shape'] = year_shape(self.life.climate_history[-365:])
                context['structure_instruction'] += ' Derive proportions and tension from this abstract curve, never calendar sections.'
            self.record['climate_structure'] = deepcopy(context)

            if method.kind == 'notagen':
                if os.environ.get('MNEMOSYNE_NOTAGEN') != 'self-hosted':
                    raise RuntimeError('NotaGen was selected but is not enabled')
                candidates = self.studio_run({'action': 'notagen', 'prompt': method.notagen_prompt}, 'notagen')
                self.record['notagen'] = candidates
                # NotaGen supplies archived reservoirs to an artist-authored cyclic plan.
                method.form = 'symphony'
                context['notagen_candidates'] = candidates
                self.record['method'] = method.model_dump()
                context['method'] = method.model_dump()
                context['candidate_images'] = []
                folder = self.root/'notagen/result'
                for i, candidate in enumerate(candidates['candidates']):
                    sk = {'id': self.work_id+f'-notagen-{i}', 'stage': 'notagen',
                          'candidate': candidate, 'files': []}
                    if candidate.get('image'):
                        image = str((folder/candidate['image']).relative_to(self.root))
                        context['candidate_images'].append(image)
                        sk['score'] = str((folder/candidate['score']).relative_to(self.root))
                    sk['files'] = [str(p.relative_to(self.root)) for p in folder.rglob('*')
                                   if p.is_file() and '.drafts' not in p.parts and
                                   (p.stem == Path(candidate['file']).stem or p.name == candidate.get('image'))]
                    self.sketches.append(sk)
                self.save()
            sketch_plan = self.plan(method, context, 'sketch-plan', sketch=True)
            sketch = self.music(sketch_plan, method, 'sketch-00')
            context['sketch'] = art_sketch(sketch)
            review = self.ask(self.system, json.dumps(context, ensure_ascii=False), Listening, 'listen:sketch',
                              images=[self.root/p for p in sketch['images']])
            context['sketch_review'] = review.model_dump()
            final = None
            for i in range(drafts):
                scale = ('форма и драматургия', 'фактура и голосоведение', 'нюансы и детали')[min(i, 2)]
                context['correction_scale'] = scale
                plan = self.plan(method, context, f'draft-plan:{i}')
                final = self.music(plan, method, f'draft-{i:02d}')
                review = self.ask(self.system, json.dumps({'context': context, 'draft': art_sketch(final),
                    'task': f'Проверь идею, метод и звучание по анализу и нотам. Исправления: {scale}. '
                            'accept только если работа завершена. Оцени, нужна ли глава Жизнеописаний.'},
                    ensure_ascii=False), Listening, f'listen:draft:{i}',
                    images=[self.root/p for p in final['images']])
                context.update(previous_plan=plan, correction=review.model_dump())
                if review.verdict == 'accept':
                    break
            if final is None:
                raise ValueError('at least one draft required')
            self.record.update(final=final['id'], verdict=review.model_dump(),
                               status='accepted' if review.verdict == 'accept' else 'unfinished')
            vector = feature_vector(final['analysis'])
            prior = [w['feature'] for w in a.catalogue if not w.get('synthetic', True)]
            novelty = min(1., min((math.dist(vector, v) for v in prior), default=1.))
            a.method, a.school = method.concept, method.school
            self.work = self.life.record_work(a.id, {'feature': vector, 'novelty': novelty,
                'quality': review.quality, 'verdict': review.verdict, 'idea': st.idea,
                'process': {'composer': deepcopy(self.record)}})
            self.work['halftones'] = shades.model_dump()
            self.life.note(a, 'composer_notebook', opus=self.work_id, notebook=self.work['notebook'])
            if review.matters:
                event = self.life.event(a, 'composer_work', work=self.work_id, verdict=review.verdict)
                self.record['chronicle_event'] = event['id']
                chronicler = ('летописец' if self.life.chronicler == f'{self.life.cluster}: chronicler of the Lives'
                             else self.life.chronicler)
                chapter = self.ask(f'Ты {chronicler}. Пиши Жизнеописания об искусстве.',
                    json.dumps({'artist': name, 'idea': st.idea, 'verdict': review.model_dump(),
                        'previous': [c['text'] for c in self.life.biographies[a.id].chapters[-4:] if c.get('text')]}, ensure_ascii=False),
                    Chapter, 'lives-chapter')
                self.life.biographies[a.id].chapters[-1]['text'] = plain(chapter.text)
                self.record['chapter'] = chapter.text
            self.save()
            if key is not None:
                self.backup(key)
            return self.record
        except PlanRejected as exc:
            self.record.update(status='plan_rejected', error=str(exc))
            return self.record
        except Exception as exc:
            self.record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            if self.work is not None:
                self.work['process']['composer'] = deepcopy(self.record)
            self.save()

    def backup(self, key):
        """Tonight's works carry the cluster's pending state pieces (never the atelier's
        own history, which is the carrier). The ledger is shared across nights."""
        from ..state.ledger import Ledger
        from ..weave import registry, schools, surface
        from ..weave import variants
        from ..weave.carry import carry
        woven = self.root/'woven'
        if self.cluster_state is None:
            report = {'reason': 'no cluster state observed tonight', 'frame_decode_verified': False}
            self.record['backup'] = report
            dump(self.root/'decode.json', report)
            self.render_final(woven)
            return
        ledger = Ledger(self.ledger_root or self.root.parent/'ledger')
        observed = ledger.observe(self.cluster_state, self.life.date(), key.public_key())
        carriers = []
        for sketch in self.sketches:
            if 'plan' not in sketch:
                continue  # NotaGen sources stay retained; their developed works carry frames.
            school = 'symphony' if sketch.get('form') == 'symphony' else sketch['plan']['school']
            for c in sketch.get('carriers') or [{'score': sketch['score']}]:
                name = sketch['id'] + (f"-mv{c['movement_index']+1}" if 'movement_index' in c else '')
                carriers.append((name, schools.prepare(surface.read(self.root/c['score']), school), school))
        entries = variants.collect({k: v for k, v in self.record.items() if k not in ('apparatus', 'backup')})
        notebook = self.work_id + '-notebook'
        if entries and variants.capacity(entries) > variants.OVERHEAD:
            carriers.insert(0, (notebook, entries, 'variants'))
        report, _ = carry(ledger, carriers, key, woven)
        report['observed'] = observed and {k: observed[k] for k in ('id', 'kind', 'at', 'k', 'target')}
        report['variant_places'] = len(variants.radices(entries))
        if notebook in report['carriers']:
            self.publish_readings(json.loads((woven/(notebook+'.variants.json')).read_text())['entries'])
        self.record['backup'] = report
        dump(self.root/'decode.json', report)
        self.render_final(woven)
        for path in woven.glob('*.musicxml'):
            registry.decode(path, key)
        for name in report['carriers']:
            original = next((s for s in self.sketches if s['id'] == name or name.startswith(s['id']+'-mv')), None)
            if original is None:
                continue  # the night's notebook carries frames in its variants
            files = [woven/(name+'.musicxml'), woven/(name+'.catalogue.json')]
            original.setdefault('files', []).extend(str(p.relative_to(self.root)) for p in files)
            original.setdefault('carried_frames', []).extend(json.loads(files[1].read_text()))
        report['post_render_decode_verified'] = True
        dump(self.root/'decode.json', report)
        if self.record.get('verdict', {}).get('verdict') == 'accept':
            self.record['status'] = ('sound_pending' if self.record.get('sound_pending') else
                                     'complete' if not report['pending_pieces'] else 'backup_carrying')

    def publish_readings(self, readings):
        """The woven reading replaces each draft text; the draft stays as the apparatus."""
        self.record['apparatus'] = {e['id']: e['markup'] for e in readings}
        for e in readings:
            target, keys = self.record, e['id'].strip('/').split('/')
            for k in keys[:-1]:
                target = target[int(k)] if isinstance(target, list) else target[k]
            last = keys[-1]
            if isinstance(target, list):
                target[int(last)] = e['text']
            else:
                target[last] = e['text']
            if e['id'] == '/chapter':
                self.life.biographies[self.artist.id].chapters[-1]['text'] = e['text']

    def render_final(self, woven):
        """Only the accepted entry sounds, and only from its woven surfaces."""
        if self.record.get('verdict', {}).get('verdict') != 'accept':
            return
        if not self.sound:
            self.record['sound'] = 'off: scores only, to be rendered or played later'
            return
        final = next(s for s in self.sketches if s['id'] == self.record['final'])
        def retained(score):
            folder = (self.root/score).parent
            assignment = folder/'orchestration.json'
            return {'plan': json.loads((folder/'plan.json').read_text()),
                    'assignment': json.loads(assignment.read_text()) if assignment.exists() else None}
        request = {'action': 'woven', 'plan': final['plan'], 'form': final.get('form', 'school'),
                   'born_schools': self.born_sources()}
        if request['form'] == 'symphony':
            movements = []
            for c in sorted(final['carriers'], key=lambda c: c['movement_index']):
                path = woven/(final['id']+f"-mv{c['movement_index']+1}.musicxml")
                if not path.exists():
                    self.record['sound_pending'] = 'final movement has no woven carrier'
                    return
                movements.append({'xml': path.read_text(), **retained(c['score'])})
            request['movements'] = movements
        else:
            path = woven/(final['id']+'.musicxml')
            if not path.exists():
                self.record['sound_pending'] = 'final work has no woven carrier'
                return
            request['xml'] = path.read_text()
            assignment = (self.root/final['score']).parent/'orchestration.json'
            request['assignment'] = json.loads(assignment.read_text()) if assignment.exists() else None
        label = 'woven-render-'+final['stage']
        result = self.studio_run(request, label)
        folder = self.root/label/'result'
        final['sounding_work'] = True
        final['audio'] = {'local_mp3': [str(p.relative_to(self.root)) for p in sorted(folder.rglob('*.mp3'))
                                      if '.drafts' not in p.parts],
                          'remote': result.get('remote'), 'lossless': ('score.flac' if request['form'] == 'symphony' else 'rendered/score.flac'),
                          'movement_lossless': [f'mv{i}/score.flac' for i in range(len(request.get('movements', [])))],
                          'lossless_policy': 'studio-only; FLAC excluded from fetch'}
        final.setdefault('files', []).extend(str(p.relative_to(self.root)) for p in folder.rglob('*')
                                            if p.is_file() and '.drafts' not in p.parts)
        self.record['sounding_work'] = final['id']


def load_state(path):
    import yaml
    from ..restore import read_archive
    if path.is_dir():
        return [d for f in sorted(path.rglob('*.y*ml')) for d in yaml.safe_load_all(f.read_text()) if d]
    if path.suffix == '.json':
        return json.loads(path.read_text())
    return read_archive(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lineage', type=Path, required=True)
    parser.add_argument('--artist')
    parser.add_argument('--scenarios', type=Path, default=Path('out/scenarios'))
    parser.add_argument('--out', type=Path, default=Path('out/works/composer'))
    parser.add_argument('--run-id', help='New notebook directory name when retaining an earlier failed attempt')
    parser.add_argument('--pod', choices=['studio-0', 'studio-1'], default='studio-0')
    parser.add_argument('--drafts', type=int, default=3)
    parser.add_argument('--no-sound', action='store_true', help='Keep the accepted work as scores; render no audio')
    parser.add_argument('--key', type=Path, required=True, help='External existing or new X25519 private key')
    parser.add_argument('--state', type=Path, help='Cluster state tonight: state.collect archive, JSON list or manifest directory')
    parser.add_argument('--ledger', type=Path, help='Shared snapshot ledger (default out/ledger/<cluster>)')
    args = parser.parse_args()
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from ..weave.backup import write_new
    life = Lineage.restore(json.loads(args.lineage.read_text()))
    a = next(a for a in life.artists if a.id == args.artist) if args.artist else \
        next(a for a in life.artists if a.status == 'working' and a.art == 'music')
    work = f'{a.id}-w{len(a.catalogue):05d}'
    if args.run_id and (Path(args.run_id).name != args.run_id or args.run_id in (".", "..")):
        parser.error("run-id must be a single directory name")
    root = args.out/a.id/(args.run_id or work)
    if root.exists():
        raise FileExistsError(f'Preserved existing notebook: {root}')
    if not args.key.exists():
        args.key.parent.mkdir(parents=True, exist_ok=True)
        write_new(args.key, X25519PrivateKey.generate().private_bytes_raw())
    key = X25519PrivateKey.from_private_bytes(args.key.read_bytes())
    studio = Studio(root, args.pod)
    night = Night(life, a.id, root, studio, backend=os.environ.get('WRITER'), sound=not args.no_sound,
                  cluster_state=load_state(args.state) if args.state else None,
                  ledger_root=args.ledger or Path('out/ledger')/life.cluster)
    studio.setup()
    inner = ideas.inner_life(args.scenarios, life.cluster, datetime.fromisoformat(life.date()))
    result = night.run(inner, drafts=args.drafts, key=key)
    print(json.dumps({'notebook': str(root), 'status': result['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
