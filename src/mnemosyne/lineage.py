"""Nightly lives, independent of words and of cluster incidents.

A small state-space model, not a lottery of preassigned biographies. All rates
are per night. Synthetic works are measurements/stubs, never artistic claims.
The same seed, inputs, parameters and version reproduce the same history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from .taste import make_taste, judge, evolve
from .reception import Reception
from .climate import qualities, temperament, feel, tendencies
from .occasions import release_night


def clip(x: float) -> float:
    return max(0., min(1., x))


LANGUAGE_NAMES = {'ru': 'Russian', 'en': 'English', 'fr': 'French', 'es': 'Spanish', 'pt': 'Portuguese',
                  'de': 'German', 'it': 'Italian', 'pl': 'Polish', 'sr': 'Serbian', 'el': 'Greek',
                  'ja': 'Japanese', 'zh': 'Chinese', 'fa': 'Persian', 'ar': 'Arabic', 'hi': 'Hindi',
                  'yo': 'Yoruba', 'la': 'Latin', 'sa': 'Sanskrit'}
# Birth languages: living literary languages, and rarer classical ones.
LANGUAGES = [('ru', 1.), ('en', 1.), ('fr', 1.), ('es', 1.), ('pt', .7), ('de', .8), ('it', .8), ('pl', .5),
             ('sr', .4), ('el', .4), ('ja', .8), ('zh', .8), ('fa', .5), ('ar', .6), ('hi', .5), ('yo', .3),
             ('la', .2), ('sa', .2)]


@dataclass(frozen=True)
class Parameters:
    # Space is for creators, per art. Silent lives are deliberately unbounded.
    spaces: int = 2
    arts: tuple = ('music', 'literature')
    # One step is one real day. Old-age survival has median near 730 days.
    maturation_min: int = 25
    maturation_max: int = 500
    maturity: int = 50
    late_age: int = 390
    old_age: int = 600
    age_hazard: float = .03
    accident: float = .000025
    heavy_nights: int = 10
    illness_rate: float = .008
    onset_nights: int = 4
    crisis_nights: int = 8
    recovery_nights: int = 12
    prolonged_nights: int = 90
    prolonged_rate: float = .5
    illness_death: float = .12
    repetition_limit: int = 45
    crisis_run: int = 8
    silence_rate: float = .025
    return_rate: float = .0007
    min_silence: int = 120
    encounter_rate: float = .002
    world_rate: float = .001
    money_rate: float = .001
    money_enabled: bool = True
    dream_rate: float = .008
    illumination_rate: float = .00003
    change_rate: float = .0008
    school_acceptance: float = .6
    synthetic_schools: bool = False
    discovery_rate: float = .035
    discovery_age: int = 90
    mastery_nights: int = 300
    silence_chapter: int = 365
    work_rate: float = .18
    drain: float = .009
    rest: float = .0018
    novelty_step: float = .08
    recognition_rate: float = .0008
    # Despair: rejected ideas and works, harsh reviews and neglect accumulate;
    # time and recognition heal. Past the threshold an artist may leave.
    despair_rejection: float = .05
    despair_review: float = .12
    despair_neglect: float = .0006
    despair_heal: float = .997
    despair_threshold: float = .6
    despair_rate: float = .01
    despair_death: float = .3

    def __post_init__(self):
        if not 1 <= self.maturation_min <= self.maturation_max:
            raise ValueError('maturation bounds must be positive and ordered')
        if not 1 <= self.spaces <= 3:
            raise ValueError('spaces must be between 1 and 3')
        for key, value in asdict(self).items():
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(f'{key} must be nonnegative')


@dataclass
class Artist:
    id: str
    name: str
    portrait: str
    birth: str
    birth_night: int
    inner_critic: dict = field(default_factory=dict)
    teachers: list[str] = field(default_factory=list)
    school: str = 'unassigned tradition'
    method: str = 'unassigned method'
    art: str = 'music'
    # The language the artist is born into: notebooks, diaries and works are written in it.
    language: str = 'ru'
    catalogue: list[dict] = field(default_factory=list)
    notebook: list[dict] = field(default_factory=list)
    periods: list[dict] = field(default_factory=list)
    health: float = 1.
    vitality: float = .8
    novelty: float = 1.
    rejections: int = 0
    repetition_run: int = 0
    unrepeated_nights: int = 0
    age: int = 0
    period: str = 'early'
    status: str = 'working'
    illness: str = ''
    illness_since: int = 0
    heavy: int = 0
    silent_since: int | None = None
    return_ready: bool = False
    death: str | None = None
    death_night: int | None = None
    master: bool = False
    wealth: float = .5
    money_met: bool = False
    recognition: float = 0.
    despair: float = 0.
    faith: float = .5
    attachment: float = .5
    pressure: float = 0.
    commerce: float = 0.
    grief: float = 0.
    isolation: float = .5
    # Stable temperament, separate from isolation imposed by external life.
    solitude: float = 0.
    skill: float = .3
    drive: float = .5
    resilience: float = .5
    openness: float = .5
    maturation: int = 100
    renounced: bool = False
    altered_voice: bool = False
    incubation: int = 0
    problem: str | None = None
    idle: int = 0
    pending_idea: dict | None = None
    pending_requiem: str | None = None
    fertility: float = 0.
    fertile_nights: int = 0
    fallow_nights: int = 0
    season: str = 'ordinary'
    style: list[float] = field(default_factory=list)
    novelty_history: list[float] = field(default_factory=list)
    sensitivity: dict = field(default_factory=dict)
    climate_state: dict = field(default_factory=dict)


@dataclass
class Biography:
    artist: str
    chronicler: str
    chapters: list[dict] = field(default_factory=list)


class LifeWords(BaseModel):
    chapter: str
    diary: str
    letter: str
    last_idea: str
    portrait: str
    name: str
    image: str


class Lineage:
    def __init__(self, cluster: str, born: datetime, seed: int = 1,
                 parameters: Parameters | None = None):
        self.cluster, self.born, self.seed = cluster, born.isoformat(), seed
        self.p = parameters or Parameters()
        self.rng = random.Random(seed)
        self.night = 0
        self.artists: list[Artist] = []
        self.biographies: dict[str, Biography] = {}
        self.events: list[dict] = []
        self.influences: list[dict] = []
        self.chronicler = f'{cluster}: chronicler of the Lives'
        self.school_attempts: list[dict] = []
        # Schools born in this atelier: manifesto, grammar source, trial, verdict, followers.
        self.schools: dict[str, dict] = {}
        self.climate = {}
        self.climate_history = []
        self.occasions = []
        self.reception = Reception(seed)
        for art in self.p.arts:
            self._birth(art=art)

    def date(self) -> str:
        return (datetime.fromisoformat(self.born) + timedelta(days=self.night)).isoformat()

    def event(self, a: Artist, kind: str, **facts) -> dict:
        e = {'id': f'e{len(self.events):06d}', 'night': self.night, 'date': self.date(),
             'artist': a.id, 'kind': kind, 'facts': facts}
        self.events.append(e)
        # Immutable snapshot: a later verdict cannot rewrite the facts supplied
        # to the chronicler at this turning point.
        recent = a.catalogue[-3:]
        chapter = {'event': e['id'], 'night': self.night, 'kind': kind,
                   'facts': json.loads(json.dumps(facts)),
                   'state': {k: getattr(a, k) for k in ('status', 'period', 'health', 'vitality',
                             'novelty', 'recognition', 'school', 'method', 'age')},
                   'works': [w['id'] for w in recent],
                   'drafts': [w['draft'] for w in recent],
                   'verdicts': [w['verdict'] for w in recent],
                   'notebook_refs': [n['id'] for n in a.notebook[-4:]],
                   'text': None, 'words': None}
        self.biographies[a.id].chapters.append(chapter)
        return e

    def note(self, a: Artist, kind: str, **facts) -> dict:
        n = {'id': f'{a.id}-note-{len(a.notebook)}', 'night': self.night, 'kind': kind, **facts}
        a.notebook.append(n)
        return n

    def _meets(self, source: Artist, target: Artist) -> bool:
        return self.rng.random() < (1 - source.solitude) * (1 - target.solitude)

    def influence(self, source: Artist, target: Artist, relation: str, weight: float):
        if relation not in ('apprenticeship', 'rebellion') and not self._meets(source, target):
            return False
        edge = {'source': source.id, 'target': target.id, 'relation': relation,
                'weight': weight, 'night': self.night, 'source_cluster': self.cluster,
                'target_cluster': self.cluster}
        self.influences.append(edge)
        if target.inner_critic:
            evolve(target.inner_critic, self.night, relation, .015 * (source.recognition - target.recognition))
        self.note(target, 'influence', **edge)
        self.event(target, 'encounter', **edge)
        # Other ateliers can supply edges in this same directed, graded schema.
        return True

    def _birth(self, teacher: Artist | None = None, art: str | None = None):
        r = self.rng
        aid = f'{self.cluster}-{len(self.artists) + 1:04d}'
        art = teacher.art if teacher is not None else (art or 'music')
        language = teacher.language if teacher is not None and r.random() < .8 else \
            r.choices([l for l, _ in LANGUAGES], weights=[w for _, w in LANGUAGES])[0]
        a = Artist(aid, aid, '[portrait awaiting words]', self.date(), self.night, art=art, language=language,
                   drive=r.random(), resilience=r.random(), openness=r.random(),
                   isolation=r.random(), skill=r.uniform(.15, .85),
                   maturation=r.randint(self.p.maturation_min, self.p.maturation_max), style=[r.random() for _ in range(4)])
        a.solitude = a.isolation ** 4
        self.artists.append(a)
        self.biographies[aid] = Biography(aid, self.chronicler)
        relation = None
        if teacher is not None and r.random() < .7 and self._meets(teacher, a):
            a.teachers.append(teacher.id)
            a.school = teacher.school
            a.method = teacher.method
            rebel = r.random() < a.openness
            if rebel:
                a.method = f'method-request-{aid}'
            relation = 'rebellion' if rebel else 'apprenticeship'
            if teacher.status == 'dead' and r.random() < .5:
                a.pending_requiem = teacher.id
        else:
            a.school = f'external-tradition-{aid}'
        a.sensitivity = temperament(a.id)
        a.inner_critic = make_taste(a.id, a.teachers)
        if teacher is not None and a.teachers:
            a.inner_critic['values'] = teacher.inner_critic['values'][:]
        a.periods.append({'night': self.night, 'period': 'early', 'method': a.method,
                          'school': a.school, 'theme': None})
        self.event(a, 'birth', teachers=a.teachers, school=a.school, apprenticeship=True,
                   stranger=not a.teachers, requiem=a.pending_requiem)
        if relation:
            self.influence(teacher, a, relation, r.uniform(.3, 1))
        return a

    def schedule(self, value):
        from .occasions import LEVELS, GENRES
        if value.get('genre') not in GENRES.values() or value.get('publicity') not in LEVELS:
            raise ValueError('invalid occasion')
        if type(value.get('moment')) is not int or value['moment'] < 0:
            raise ValueError('invalid occasion moment')
        self.occasions.append({k: value[k] for k in ('genre', 'moment', 'publicity')})

    def working(self):
        return [a for a in self.artists if a.status in ('working', 'ill')]

    def change(self, a: Artist, cause: str, radical: bool = False):
        a.period = 'late' if a.age >= self.p.late_age or a.illness or a.silent_since is not None else 'mature'
        a.method = f'{a.id}-method-{len(a.periods)}'
        a.style = [self.rng.random() for _ in a.style]
        evolve(a.inner_critic, self.night, cause, self.rng.uniform(-.08, .08))
        if radical:
            request = {'artist': a.id, 'night': self.night, 'cause': cause,
                       'status': 'awaiting artistic method and inner-critic judgement'}
            self.school_attempts.append(request)
            # Hook for artist.method(... allow_invention=True) / save_invented.
            # A request is NOT an accepted school.
            if self.p.synthetic_schools and self.rng.random() < self.p.school_acceptance:
                # Only the synthetic catalogue uses this surrogate verdict.
                # It creates no artistic doctrine and writes nothing to atlas/.
                a.school = f'synthetic-school-{a.id}-{len(a.periods)}'
                request['synthetic_verdict'] = 'accept'
                self.event(a, 'school', school=a.school, synthetic=True)
        a.periods.append({'night': self.night, 'period': a.period, 'method': a.method,
                          'school': a.school, 'theme': None, 'cause': cause})
        self.note(a, 'period', cause=cause, method=a.method, theme_request=True)
        self.event(a, 'period', cause=cause, radical=radical, method=a.method)

    def accept_school(self, artist: str, school: str, judgement: str):
        """Explicit hook: only a reviewed artistic method becomes a school."""
        if judgement != 'accept':
            raise ValueError('school requires acceptance')
        a = next(a for a in self.artists if a.id == artist)
        a.school = school
        self.event(a, 'school', school=school)

    def _silence(self, a: Artist, cause: str):
        a.status, a.silent_since = 'silent', self.night
        a.return_ready = False
        self.event(a, 'silence', cause=cause)

    def _die(self, a: Artist, cause: str, work_source: Callable | None = None):
        if a.status == 'dead':
            return
        self.event(a, 'secret_miracle', cause=cause)
        # Finishing is before death, even for a previously silent artist.
        self._work(a, last=True, observation=work_source(a, True) if work_source else None)
        a.status, a.death, a.death_night = 'dead', self.date(), self.night
        self.event(a, 'death', cause=cause, last_work=a.catalogue[-1]['id'])
        related = {e['source'] for e in self.influences if e['target'] == a.id}
        related |= {e['target'] for e in self.influences if e['source'] == a.id}
        for other in self.artists:
            if other.status != 'dead' and (a.id in other.teachers or other.id in related):
                other.grief = clip(other.grief + .5)
                self.event(other, 'bereavement', deceased=a.id)

    def _forces(self, a: Artist, q: dict):
        r, p = self.rng, self.p
        a.sensitivity = a.sensitivity or temperament(a.id)
        previous = a.climate_state
        q = feel(q, a.sensitivity)
        a.climate_state = q
        a.inner_critic['climate'] = {'severity': q['loss']*.15, 'risk': q['steadiness']*.15}
        a.fertility += .003*(q['novelty']-.5) + .002*(q['crowding']-.5)*a.sensitivity['crowding_energy']
        if previous.get('turbulence', 0) > .5 and q['steadiness'] > .6:
            a.incubation += 10
        heavy = sum(q.get(k, 0) for k in ('strain', 'loss', 'scars', 'turbulence')) / 4
        a.heavy = a.heavy + 1 if heavy > .55 else max(0, a.heavy - 2)
        a.grief *= .997
        a.pressure *= .995
        a.attachment += (.5 - a.attachment) * .001
        a.fertility = .995 * a.fertility + r.gauss(0, .025)
        a.skill = clip(a.skill + .00015 * a.openness)
        a.recognition *= .999
        # Renewal, steadiness and company heal; isolation slows it.
        a.despair *= 1 - (1 - p.despair_heal) * (q['renewal'] + q['steadiness'] + 1 - a.isolation) / 1.5
        if a.recognition < .05 and sum(w['verdict'] == 'accept' for w in a.catalogue) >= 3:
            self._wound(a, p.despair_neglect)
        a.commerce = clip(a.commerce * .998 + (.001 * a.recognition * a.wealth if a.money_met else 0))
        a.vitality = clip(a.vitality + p.rest * (.3 + a.resilience) - .0008 * a.grief
                          - .0006 * heavy - .0005 * a.pressure)
        if a.money_met:
            a.wealth = clip(a.wealth - .0004)
            a.vitality = clip(a.vitality - .0007 * max(0, .3 - a.wealth))
        a.health = clip(a.health + .001 if not a.illness else a.health)
        others = [b for b in self.artists if b.id != a.id]
        if others and r.random() < p.encounter_rate * (1 - a.isolation):
            b = r.choice(others)
            relation = r.choice(['friendship', 'rivalry', 'borrowed_method', 'answered_work', 'quarrel'])
            if self.influence(b, a, relation, r.random()):
                if relation == 'borrowed_method' and b.school in self.schools and a.school != b.school \
                        and r.random() < a.openness:
                    a.school = b.school
                    self.schools[b.school].setdefault('followers', []).append(a.id)
                    self.event(a, 'joined_school', school=b.school, founder=self.schools[b.school]['author'], via=b.id)
                a.pressure = clip(a.pressure + (.3 if relation in ('rivalry', 'quarrel') else -.1))
                a.vitality = clip(a.vitality + .1)
                if r.random() < a.openness:
                    self.change(a, relation)
        if r.random() < p.world_rate:
            # External life is felt, never a cluster event translated into an object.
            force = r.choice(['beloved', 'exile', 'faith', 'lost_work', 'world', 'walk'])
            if force == 'beloved':
                a.attachment = r.random()
                a.vitality = clip(a.vitality + (a.attachment - .5) * .4)
            elif force == 'faith':
                a.faith = r.random()
                if a.faith < .1 and a.drive < .35:
                    a.renounced = True
                    self._silence(a, 'renunciation')
            elif force == 'exile':
                a.isolation = clip(a.isolation + .3)
                a.grief = clip(a.grief + .3)
            elif force == 'lost_work' and a.catalogue:
                # Loss in the story must never destroy the backup.
                self.note(a, 'lost_work', work=r.choice(a.catalogue)['id'], archive_retained=True)
                a.grief = clip(a.grief + .2)
            else:
                a.incubation += 14
            self.event(a, force, faith=a.faith, attachment=a.attachment, grief=a.grief)
        if p.money_enabled and r.random() < p.money_rate:
            a.money_met = True
            source = r.choices(['commission', 'patron', 'poverty'], weights=[.2+q['renewal'], .2+q['abundance'], 1.2-q['abundance']])[0]
            a.wealth = clip(a.wealth + (-.4 if source == 'poverty' else .35))
            a.pressure = clip(a.pressure + .15)
            self.event(a, source, wealth=a.wealth)
        if a.teachers:
            teacher = next((b for b in self.artists if b.id == a.teachers[0]), None)
            if teacher and a.skill > teacher.skill + .2 and not any(
                    e['kind'] == 'surpassed' and e['artist'] == a.id for e in self.events):
                teacher.pressure = clip(teacher.pressure + .4)
                self.event(a, 'surpassed', teacher=teacher.id)
                self.event(teacher, 'surpassed_by_student', student=a.id)

    def _dreams(self, a: Artist):
        r, p = self.rng, self.p
        if a.pending_idea is None:
            if a.incubation == 0:
                self.note(a, 'preparation', problem=a.problem, synthetic=a.problem is None)
                self.note(a, 'incubation', problem=a.problem)
            a.incubation += 1
        if r.random() < p.dream_rate:
            self.note(a, 'dream', image=None, theme=None, words_pending=True)
            a.incubation += 20
            self.event(a, 'dream', incubation=a.incubation)
        probability = min(.04, p.illumination_rate * a.incubation * (1 + min(a.idle, 100) / 100))
        if a.pending_idea is None and a.incubation > 20 and r.random() < probability:
            a.pending_idea = {'id': f'{a.id}-insight-{self.night}', 'strength': .95,
                              'idea': None, 'problem': a.problem,
                              'stage': 'illumination', 'incubated': a.incubation}
            self.note(a, 'illumination', **a.pending_idea)
            self.event(a, 'illumination', **a.pending_idea)
            a.incubation = 0

    def _wound(self, a: Artist, amount: float):
        # The cluster's felt climate is the weather a blow lands in, not its cause:
        # the same review hurts more in heavy times and for a fragile character.
        q = a.climate_state or {}
        weather = .5 + sum(q.get(k, .5) for k in ('strain', 'loss', 'scars', 'turbulence')) / 4
        a.despair = clip(a.despair + amount * (1.3 - a.resilience) * weather)

    def set_aside_idea(self, artist: str, idea: str, reasons: str = ''):
        """A night whose idea the inner critic refused: kept as a problem to incubate."""
        a = next(a for a in self.artists if a.id == artist)
        a.rejections += 1
        a.problem = idea
        self._wound(a, self.p.despair_rejection)
        self.note(a, 'set_aside', idea=idea, reasons=reasons, despair=a.despair)

    def found_school(self, artist: str, record: dict) -> dict:
        """An accepted grammar becomes a school of this atelier, founded by the artist."""
        a = next(a for a in self.artists if a.id == artist)
        record = {**deepcopy(record), 'author': a.id, 'night': self.night, 'date': self.date(),
                  'followers': [], 'status': 'accepted'}
        self.schools[record['id']] = record
        a.school = record['id']
        self.school_attempts.append({'artist': a.id, 'night': self.night, 'status': 'born', 'school': record['id']})
        self.note(a, 'school_birth', school=record['id'], name=record['name'])
        self.event(a, 'school_birth', school=record['id'], name=record['name'])
        return record

    def school_unborn(self, artist: str, name: str, history: list):
        """A school that did not pass its trial or its critic stays in the notebooks."""
        a = next(a for a in self.artists if a.id == artist)
        self.school_attempts.append({'artist': a.id, 'night': self.night, 'status': 'unborn', 'name': name,
                                     'rounds': len(history)})
        self.note(a, 'school_unborn', name=name, attempts=deepcopy(history))
        self._wound(a, self.p.despair_rejection)

    def idea_seed(self, artist: str) -> dict | None:
        """Pass this seed into the idea stage; it must still face its inner critic."""
        a = next(a for a in self.artists if a.id == artist)
        return json.loads(json.dumps(a.pending_idea)) if a.pending_idea else None

    def record_work(self, artist: str, observation: dict):
        """Commit a real producer observation at the current night."""
        a = next(a for a in self.artists if a.id == artist)
        if a.status not in ("working", "ill"):
            raise ValueError("only a living working artist can compose")
        return self._work(a, observation=observation)

    def _work(self, a: Artist, last: bool = False, observation: dict | None = None):
        """Record a measured work, or use the explicitly synthetic surrogate.

        A real producer supplies feature, novelty (against its own catalogue),
        quality, verdict and optionally idea/process. It owns art and criticism;
        the fate engine owns the consequences. No Writer decides a life event.
        """
        if a.status == 'dead':
            raise ValueError('the dead cannot work')
        r, p = self.rng, self.p
        insight = a.pending_idea
        drafts = []
        if observation is None:
            spread = p.novelty_step * (.25 + a.openness) * (1 - .8 * a.commerce)
            if insight:
                spread += .3
            feature = [clip(x + r.gauss(0, spread)) for x in a.style]
            novelty = min((math.dist(feature, w['feature']) for w in a.catalogue), default=1.)
            novelty = clip(novelty / .25)
            maturity = min(1., a.age / a.maturation)
            quality = clip(.35 * a.skill + .3 * a.vitality + .25 * maturity + .2 * a.fertility
                           + (.2 if insight else 0) + r.gauss(0, .12))
            for draft in range(3):
                honest, verdict = judge(a.inner_critic, quality, novelty, r)
                drafts.append(dict(number=draft, quality=quality, inner_view=honest, verdict=verdict))
                if verdict == 'accept' or r.random() < .4 or draft == 2:
                    break
                quality = clip(quality + r.gauss(.015, .12))
        else:
            feature, novelty, quality, verdict = (observation[k] for k in ('feature', 'novelty', 'quality', 'verdict'))
            if verdict not in ('accept', 'rewrite', 'repetition') or not (0 <= novelty <= 1 and 0 <= quality <= 1):
                raise ValueError('invalid work observation')
            if len(feature) != len(a.style) or not all(math.isfinite(x) for x in feature):
                raise ValueError('invalid feature vector')
        if observation is not None:
            honest = observation.get('inner_view', quality)
        merit = clip(.8 * quality + .2 * honest + r.gauss(0, .08))
        a.novelty_history.append(novelty)
        a.novelty = sum(a.novelty_history[-12:]) / len(a.novelty_history[-12:])
        a.rejections = 0 if verdict == 'accept' else a.rejections + 1
        if verdict == 'accept':
            a.despair *= .7
        else:
            self._wound(a, p.despair_rejection)
        a.repetition_run = a.repetition_run + 1 if verdict == 'repetition' else 0
        if verdict == 'repetition':
            a.unrepeated_nights = 0
        wid = f'{a.id}-w{len(a.catalogue):05d}'
        work = {'id': wid, 'night': self.night, 'feature': feature, 'novelty': novelty,
                'quality': quality, 'merit': merit, 'inner_view': honest, 'verdict': verdict, 'period': a.period, 'method': a.method,
                'school': a.school, 'draft': f'{wid}-draft', 'notebook': f'{wid}-notebook',
                'kind': 'last_piece' if last else 'requiem' if a.pending_requiem else 'study',
                'requiem_for': a.pending_requiem, 'idea_seed': insight,
                'idea': observation.get('idea') if observation else None, 'synthetic': observation is None,
                'process': observation.get('process', {}) if observation else {'drafts': drafts},
                'halftones': {'health': a.health, 'grief': a.grief, 'vitality': a.vitality,
                             'poverty': 1 - a.wealth if a.money_met else None},
                'influences': [e for e in self.influences if e['target'] == a.id][-5:]}
        work['birth_climate'] = dict(self.climate)
        work['structural_tendencies'] = tendencies(a.climate_state or self.climate, a.inner_critic, a.method, r)
        eligible = next((o for o in self.occasions if o["moment"] <= self.night), None)
        if eligible:
            occasion = eligible
            self.occasions.remove(eligible)
            work.update(kind=occasion['genre'], publicity=occasion['publicity'],
                        publish_after=release_night(max(self.night, occasion['moment']), occasion['publicity']))
        first = verdict == 'accept'  and not any(w['verdict'] == 'accept' for w in a.catalogue)
        a.catalogue.append(work)
        a.inner_critic['proud_of' if verdict == 'accept' else 'ashamed_of'].append(wid)
        self.note(a, 'draft_decision', work=wid, inner_view=honest, verdict=verdict,
                  taste=dict(threshold=a.inner_critic['threshold'], values=a.inner_critic['values'][:]),
                  retained=True, stage='left' if verdict == 'accept' else 'abandoned')
        self.note(a, 'verification', work=wid, verdict=verdict, seed=insight)
        a.pending_idea, a.pending_requiem, a.idle = None, None, 0
        a.vitality = clip(a.vitality - p.drain * (.3 + 2 * a.drive) * (1.3 - a.resilience))
        if first or last:
            self.event(a, 'last_work' if last else 'first_accepted', work=wid, verdict=verdict)
        if insight:
            self.event(a, 'verification', work=wid, verdict=verdict)
        return work

    def _illness(self, a: Artist, work_source: Callable | None = None):
        p, r = self.p, self.rng
        if a.illness == 'changed':
            return
        if not a.illness:
            if a.heavy >= p.heavy_nights and (a.rejections >= p.crisis_run or a.vitality < .2) and a.vitality < .4 \
                    and r.random() < p.illness_rate:
                a.illness, a.illness_since = 'onset', self.night
                a.status = 'ill' if a.status != 'silent' else 'silent'
                self.event(a, 'illness_onset')
            return
        elapsed = self.night - a.illness_since
        a.health = clip(a.health - (.008 if a.illness == 'crisis' else .002))
        if a.illness == 'onset' and elapsed >= p.onset_nights:
            a.illness, a.illness_since = 'crisis', self.night
            self.event(a, 'illness_crisis')
        elif a.illness == 'crisis' and elapsed >= p.crisis_nights:
            if r.random() < p.illness_death * (1.5 - a.resilience):
                self._die(a, 'illness', work_source)
            elif r.random() < p.prolonged_rate * (1 - a.resilience):
                a.illness, a.illness_since = 'prolonged', self.night
                self.event(a, 'illness_prolonged')
            else:
                a.illness, a.illness_since = 'recovery', self.night
                self.change(a, 'illness')
                self.event(a, 'illness_recovery', altered_voice=a.altered_voice)
        elif a.illness == 'prolonged' and elapsed >= p.prolonged_nights:
            a.illness, a.illness_since = 'changed', self.night
            a.altered_voice = True
            a.health = .6
            a.vitality = clip(a.vitality + .35)
            self.change(a, 'illness')
            # Keep the archival event key used by retrospective readers, but
            # distinguish adaptation from recovery: no recovered event follows.
            self.event(a, 'illness_recovery', altered_voice=True, outcome='changed_voice',
                       prolonged_nights=elapsed)
            if a.status == 'silent' and not a.renounced:
                a.return_ready = True
        elif a.illness == 'recovery' and elapsed >= p.recovery_nights:
            a.illness, a.health = '', .8
            if a.status == 'ill':
                a.status = 'working'
            self.event(a, 'recovered')

    def step(self, mood: dict, work_source: Callable | None = None):
        """Advance one night; optional work_source(artist, last) supplies verdicts.

        Replaying real production requires the same recorded observations,
        alongside mood, parameters, seed and engine version.
        """
        q = qualities(mood)
        self.climate = q
        self.climate_history.append(dict(q))
        self.night += 1
        r, p = self.rng, self.p
        # Only qualities cross this boundary, never facts/ops/pod incidents.
        for a in list(self.artists):
            if a.status == 'dead':
                continue
            a.age = self.night - a.birth_night
            if a.status in ('working', 'ill'):
                a.unrepeated_nights += 1
            self._forces(a, q)
            self._dreams(a)
            self._illness(a, work_source)
            if a.status == 'dead':
                continue
            hazard = p.accident + p.age_hazard * max(0, (a.age - p.old_age) / 365)
            if a.repetition_run >= p.repetition_limit and a.status != 'silent':
                self._silence(a, 'repetition')
                a.repetition_run = 0
                continue
            if r.random() < hazard:
                self._die(a, 'old_age' if a.age > p.old_age else 'chance', work_source)
                continue
            if a.status != 'silent' and a.despair >= p.despair_threshold \
                    and r.random() < p.despair_rate * (1.5 - a.resilience):
                if r.random() < p.despair_death:
                    self._die(a, 'despair', work_source)
                else:
                    a.renounced = True
                    self._silence(a, 'despair')
                continue
            if a.status == 'silent':
                duration = self.night - a.silent_since
                a.idle += 1
                if duration and duration % p.silence_chapter == 0:
                    self.event(a, 'years_of_silence', duration=duration)
                if not a.renounced and duration >= p.min_silence \
                        and r.random() < p.return_rate * (a.vitality + a.openness):
                    a.return_ready = True
                continue
            if not a.master and a.unrepeated_nights >= p.mastery_nights and any(
                    w['verdict'] == 'accept' for w in a.catalogue):
                a.master = True
                self.event(a, 'master', unrepeated_nights=a.unrepeated_nights)
            if a.age == p.maturity or a.age == p.late_age:
                a.period = 'mature' if a.age == p.maturity else 'late'
                a.periods.append({'night': self.night, 'period': a.period, 'method': a.method,
                                  'school': a.school, 'theme': None})
                self.event(a, 'period', cause='age')
            falling = len(a.novelty_history) >= 12 and sum(a.novelty_history[-6:]) < sum(a.novelty_history[-12:-6])
            crisis = a.rejections >= p.crisis_run and falling
            if a.vitality < .18 or crisis:
                if r.random() < p.silence_rate:
                    if crisis and r.random() < a.openness:
                        self.change(a, 'creative_crisis', radical=True)
                        a.vitality = clip(a.vitality + .15)
                    else:
                        self._silence(a, 'exhaustion' if a.vitality < .18 else 'repetition')
                        continue
            if r.random() < p.change_rate * a.openness * (1 + a.pressure + a.grief):
                self.change(a, 'inner_change', radical=r.random() < .2)
            strength = a.vitality + a.fertility + .3 * min(1, a.age / a.maturation)
            a.fertile_nights = a.fertile_nights + 1 if strength > 1.25 else 0
            a.fallow_nights = a.fallow_nights + 1 if strength < .45 else 0
            season = 'mirabilis' if a.fertile_nights >= 60 else 'fallow' if a.fallow_nights >= 60 else 'ordinary'
            if season != a.season:
                a.season = season
                self.event(a, 'fertility', season=season)
            chance = p.work_rate * (.2 + 2 * a.drive) * max(.15, 1 + a.fertility)
            if r.random() < chance:
                self._work(a, observation=work_source(a, False) if work_source else None)
            else:
                a.idle += 1
        self.reception.step(self)
        # Fill one empty space nightly. Return gets first refusal; silent artists
        # remain alive and are not evicted from the book.
        for art in p.arts:
            if len([a for a in self.working() if a.art == art]) >= p.spaces:
                continue
            returning = [a for a in self.artists if a.art == art and a.status == 'silent'
                         and a.return_ready and not a.renounced]
            if returning:
                a = r.choice(returning)
                self.change(a, 'return')
                a.status = 'ill' if a.illness else 'working'
                self.event(a, 'return', silence=self.night - a.silent_since)
                a.silent_since, a.return_ready = None, False
                continue
            predecessors = [a for a in self.artists if a.art == art and (a.status in ('dead', 'silent') or a.master)]
            self._birth(r.choice(predecessors) if predecessors else None, art=art)

    def state(self) -> dict:
        return {'version': 2, 'climate': self.climate, 'climate_history': self.climate_history, 'occasions': self.occasions, 'reception': self.reception.state(), 'cluster': self.cluster, 'born': self.born, 'seed': self.seed,
                'night': self.night, 'parameters': asdict(self.p), 'rng': self.rng.getstate(),
                'artists': [asdict(a) for a in self.artists], 'events': self.events,
                'biographies': {k: asdict(v) for k, v in self.biographies.items()},
                'influences': self.influences, 'chronicler': self.chronicler,
                'school_attempts': self.school_attempts, 'schools': self.schools}

    @classmethod
    def restore(cls, data: dict) -> Lineage:
        if data['version'] not in (1, 2):
            raise ValueError('unsupported lineage version')
        self = cls.__new__(cls)
        self.cluster, self.born, self.seed, self.night = (data[k] for k in ('cluster', 'born', 'seed', 'night'))
        parameters = dict(data['parameters'])
        # Checkpoints predating the two-year calibration keep their birth clock.
        parameters.setdefault('maturation_min', 90)
        parameters.setdefault('maturation_max', 1800)
        # Checkpoints from before literature keep a single art.
        parameters['arts'] = tuple(parameters.get('arts', ('music',)))
        self.p = Parameters(**parameters)
        self.rng = random.Random()
        def tuples(x):
            return tuple(tuples(v) for v in x) if isinstance(x, (list, tuple)) else x
        self.rng.setstate(tuples(data['rng']))
        self.climate = qualities(data['climate']) if data.get('climate') else {}
        self.climate_history = [qualities(q) for q in data.get('climate_history', [])]
        self.occasions = deepcopy(data.get('occasions', []))
        self.artists = [Artist(**deepcopy(a)) for a in data['artists']]
        self.reception = Reception.restore(data['reception']) if data['version'] == 2 else Reception(self.seed)
        if data['version'] == 1:
            # Preserve legacy archives; reception starts now under version 2 rules.
            for artist in self.artists:
                artist.inner_critic = artist.inner_critic or make_taste(artist.id, artist.teachers)
                for work in artist.catalogue:
                    work.setdefault('merit', work['quality'])
                    work.setdefault('inner_view', work['quality'])
                    self.reception.register(artist, work)
        self.biographies = {k: Biography(**v) for k, v in data['biographies'].items()}
        for key in ('events', 'influences', 'chronicler', 'school_attempts'):
            setattr(self, key, deepcopy(data[key]))
        self.schools = deepcopy(data.get('schools', {}))
        return self

    @classmethod
    def from_objects(cls, objects: list[dict], cluster: str) -> Lineage:
        """Restore directly from the namespaced objects saved by Atelier."""
        from .atelier import is_atelier_object
        objects = [o for o in objects if is_atelier_object(o)]
        roots = [o['spec'] for o in objects if o['kind'] == 'Atelier'
                 and o['spec'].get('lineage', {}).get('cluster') == cluster]
        if len(roots) != 1:
            raise ValueError('expected one lineage root')
        root = roots[0]
        artists = {o['metadata']['name']: o['spec'] for o in objects if o['kind'] == 'Artist'}
        biographies = {o['metadata']['name']: {k: v for k, v in o['spec'].items() if k != 'book'}
                       for o in objects if o['kind'] == 'Biography'}
        return cls.restore(json.loads(json.dumps({**root['lineage'],
                           'artists': [artists[k] for k in root['artists']],
                           'biographies': {k: biographies[k] for k in root['artists']}})))

    def write_words(self, writer_factory: Callable | None = None):
        """Rendering only; cannot roll RNG, change a verdict, or alter fate."""
        if writer_factory is None:
            from .literature import Writer
            writer_factory = lambda nb: Writer(nb, role="chronicler", data_class="art")
        chronicler = 'летописец' if self.chronicler == f'{self.cluster}: chronicler of the Lives' else self.chronicler
        system = (f'Ты {chronicler}. Единый голос жизнеописаний в духе Вазари, не журнал событий. '
                  'Можно быть пристрастным, ошибаться в толковании, создавать легенду, но не менять факты судьбы. '
                  'Не упоминай инфраструктуру. Напиши главу; diary — голос художника; letter — только при болезни; '
                  'last_idea — только для последней работы; name и portrait — при рождении; image — для сна или озарения. '
                  'Остальные поля оставь пустыми. Художественные обстоятельства не являются буквальными объектами произведения.')
        for a in self.artists:
            biography = self.biographies[a.id]
            for chapter in biography.chapters:
                if chapter['text'] is not None:
                    continue
                notes = [n for n in a.notebook if n['id'] in chapter['notebook_refs']]
                context = {'name': 'художник' if a.name == a.id else a.name, 'portrait': a.portrait,
                           'kind': chapter['kind'],
                           'catalogue': [{k: w[k] for k in ('idea', 'method', 'halftones') if k in w}
                                         for w in a.catalogue if w['id'] in chapter['works']],
                           'previous_chapters': [c['text'] for c in biography.chapters
                                                 if c['text'] is not None][-3:]}
                nb = []
                words = writer_factory(nb).ask(system, json.dumps(context, ensure_ascii=False),
                                               LifeWords, f"life:{a.id}:{chapter['event']}")
                chapter['text'], chapter['words'] = words.chapter, words.model_dump()
                self.note(a, 'life_words', event=chapter['event'], words=words.model_dump(), drafts=nb)
                if chapter['kind'] == 'birth':
                    from .weave.variants import plain
                    a.name, a.portrait = words.name or a.name, plain(words.portrait) or a.portrait
                if chapter['kind'] == 'last_work' and words.last_idea:
                    next(w for w in a.catalogue if w['id'] == chapter['facts']['work'])['idea'] = words.last_idea
                if chapter['kind'] == 'illumination' and a.pending_idea and words.image:
                    a.pending_idea['idea'] = words.image

    def markdown(self) -> str:
        lines = [f'# Жизнеописания: {self.cluster}', '', f'Летописец: {self.chronicler}', '',
                 'Синтетический опыт: оценки и работы — заглушки; факты судеб определяет движок.', '']
        for a in self.artists:
            lines += [f'## {a.name}', '', f'Рождение: {a.birth}; статус: {a.status}; возраст: {a.age} ночей.',
                      f'Учителя: {", ".join(a.teachers) or "другая традиция"}. Школа: {a.school}.', '', a.portrait, '']
            for c in self.biographies[a.id].chapters:
                lines += [f"### Ночь {c['night']}: {c['kind']}", '', c['text'] or
                          'Заготовка главы. Факты для летописца: ' + json.dumps(
                              {k: c[k] for k in ('facts', 'state', 'works', 'drafts', 'verdicts', 'notebook_refs')},
                              ensure_ascii=False), '']
        return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('clusters', nargs='*', default=['leonia', 'bank'])
    ap.add_argument('--scenarios', type=Path, default=Path('out/scenarios'))
    ap.add_argument('--out', type=Path, default=Path('out/works/lineage'))
    ap.add_argument('--seed', type=int, default=17)
    ap.add_argument('--nights', type=int, default=365)
    ap.add_argument('--words', action='store_true')
    args = ap.parse_args()
    from .mood import mood
    from .atelier import Atelier
    args.out.mkdir(parents=True, exist_ok=True)
    for cluster in args.clusters:
        facts = json.loads((args.scenarios / cluster / 'facts.json').read_text())
        born = datetime.fromisoformat(facts['start'])
        seed = args.seed + int.from_bytes(hashlib.sha256(cluster.encode()).digest()[:4])
        life = Lineage(cluster, born, seed, Parameters(synthetic_schools=True))
        for n in range(args.nights):
            life.step(mood(args.scenarios, cluster, born + timedelta(days=n + 1)))
            if args.words:
                life.write_words()
        (args.out / f'{cluster}.json').write_text(json.dumps(life.state(), ensure_ascii=False, indent=1))
        (args.out / f'{cluster}.md').write_text(life.markdown())
        atelier = Atelier(cluster, args.out / 'atelier')
        atelier.lineage(life)
        atelier.write()
        print(cluster, 'nights=', life.night, 'artists=', len(life.artists),
              'deaths=', sum(a.status == 'dead' for a in life.artists), 'chapters=', len(life.events), flush=True)


if __name__ == '__main__':
    main()
