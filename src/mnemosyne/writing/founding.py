"""A literature school born in the atelier: a writer finds no school that holds the idea and founds one.

The founding is part of the night. The writer writes the new school's poetics
in the same shape as the schools of the atlas (manifesto, lineage, worldview,
reader, time, composition, voice, language, devices, prohibitions, markers),
their inner critic asks whether it is only a renaming of a known school and
whether it holds together, and, once accepted, the writer writes the first
work in it the same night. Other writers then meet it in their library.

The form such a school checks is deliberately small: prose or verse and a
length. Everything else is its poetics, read by the writer and the critics.
"""
from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel

from . import poetics


class Poetics(BaseModel):
    name: str
    manifesto: list[str]
    predecessors: str
    against: str
    worldview: str
    reader: str
    time: str
    composition: str
    narrator: str
    character: str
    language: str
    imagery: str
    themes: str
    devices: str
    genres: str
    forbidden: list[str]
    markers: list[str]
    reading: str
    kind: Literal['prose', 'poetry']
    min_words: int
    max_words: int


class Judgement(BaseModel):
    verdict: Literal['accept', 'rewrite']
    renaming_of: str
    reasons: str
    corrections: list[str]


CJK = re.compile(r'[぀-ヿ㐀-鿿가-힯]')


def words(text: str) -> int:
    """Words, with two CJK characters counted as one word."""
    cjk = len(CJK.findall(text))
    return len(re.findall(r'\w+', CJK.sub(' ', text))) + cjk // 2


class BornSchool:
    """A born school with the interface of the coded ones: KIND, RULES, EXAMPLE_PLAN, skeleton, check."""

    def __init__(self, key: str, record: dict):
        p = record['poetics']
        self.key, self.KIND = key, p.get('kind', 'prose')
        self.min_words = max(30, int(p.get('min_words') or 200))
        self.max_words = max(self.min_words + 50, int(p.get('max_words') or 2500))
        self.RULES = (f'{"Prose" if self.KIND == "prose" else "Verse"} of {self.min_words}–{self.max_words} words; '
                      'everything else is the poetics of the school, not a mechanical form.')
        self.EXAMPLE_PLAN = {'school': key, 'title': '', 'seed': 1}

    def skeleton(self, plan, rng):
        return {'kind': self.KIND, 'min_words': self.min_words, 'max_words': self.max_words}

    def check(self, text, frame, language):
        n = words(text)
        if n < frame['min_words'] * .8:
            return [f'{n} words; at least {frame["min_words"]}']
        if n > frame['max_words'] * 1.15:
            return [f'{n} words; at most {frame["max_words"]}']
        return []


def atlas_form(p: Poetics) -> dict:
    """The poetics in the atlas schema, so pages, prompts and critics read it like any other school."""
    d = p.model_dump()
    return {'name': d['name'], 'art': 'literature', 'manifesto': d['manifesto'],
            'lineage': {'predecessors': d['predecessors'], 'against': d['against']},
            **{k: d[k] for k in ('worldview', 'reader', 'time', 'composition', 'narrator', 'character', 'language',
                                 'imagery', 'themes', 'devices', 'genres', 'forbidden', 'markers', 'reading',
                                 'kind', 'min_words', 'max_words')}}


def adopt(life) -> dict:
    """Born literature schools of this life as coded schools; their poetics become readable by name."""
    born = {}
    for key, record in list(life.schools.items()):
        if record.get('art') == 'literature' and record.get('status') == 'accepted':
            poetics.BORN[key] = record['poetics']
            born[key] = BornSchool(key, record)
    return born


def schools(life) -> dict:
    from .schools import SCHOOLS
    return {**SCHOOLS, **adopt(life)}


def found(night, idea: str, method, known: dict) -> tuple[dict | None, list]:
    """Up to three rounds of poetics and the inner critic's judgement. Returns (record, history)."""
    from .. import artist as ideas
    a = night.artist
    others = '\n'.join(f'- {(poetics.load(k) or {}).get("name", k)}: {poetics.brief(k, getattr(s, "RULES", ""))}'
                       for k, s in known.items())
    history, corrections = [], []
    for n in range(3):
        p = night.ask(night.system,
                      f'{idea}\n\nТы решил основать школу «{method.school}», потому что: {method.reason}\n\n'
                      f'Школы, которые уже есть:\n{others}\n\n'
                      'Напиши поэтику новой школы так, как пишут о настоящих литературных школах: манифест '
                      '(пять–семь положений, твоим голосом), от кого она идёт и с кем спорит, картина мира, '
                      'какого читателя она ждёт, как в ней течёт время, как строится вещь, кто говорит, что такое '
                      'персонаж, какой язык, какие образы и темы, приёмы и жанры, чего она никогда не делает '
                      '(forbidden), по чему её узнают (markers), и что в ней значит «понятно и интересно» (reading). '
                      'kind: prose или poetry; min_words и max_words — разумный объём одной вещи этой школы. '
                      'Пиши на родном языке.'
                      + ('\n\nЧто поправить после прошлого чтения:\n- ' + '\n- '.join(corrections) if corrections else ''),
                      Poetics, f'school-poetics:{n}')
        judged = night.ask(ideas.taste_prompt(a.inner_critic) +
                           'Суди новую школу строго. Не переименование ли это известной школы — из списка или из '
                           'истории литературы (назови её в renaming_of, иначе пусто)? Держится ли картина мира, '
                           'вытекают ли из неё время, голос, язык и запреты? Можно ли по markers узнать её текст? '
                           'Плодотворна ли она больше чем для одного замысла? accept или rewrite; в corrections — '
                           'что именно переписать.',
                           f'Существующие школы:\n{others}\n\nНовая школа:\n{p.model_dump_json()}',
                           Judgement, f'school-critic:{n}')
        history.append({'poetics': p.model_dump(), 'judgement': judged.model_dump()})
        if judged.verdict == 'accept':
            key = 'born-' + hashlib.sha256(f'{a.id}:{p.name}'.encode()).hexdigest()[:10]
            return {'id': key, 'name': p.name, 'art': 'literature', 'poetics': atlas_form(p),
                    'manifesto': {'manifesto': p.manifesto}, 'reason': method.reason}, history
        corrections = judged.corrections + ([f'Это пока «{judged.renaming_of}» под другим именем.']
                                            if judged.renaming_of else [])
    return None, history
