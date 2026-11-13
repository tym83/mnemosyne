"""A school as a poetics: worldview, reader, time, composition, voice, language, devices, prohibitions.

The form a school's code checks is one axis of it. The rest is read from
atlas/literature/poetics/<school>.yaml and given to the writer as words: what
the school believes, how it builds, what it never does, and how a reader of
this school knows a text is alive. A school without a poetics file falls back
to its rules of form.
"""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

import yaml

ATLAS = Path(os.environ.get('MNEMO_ASSETS') or Path(__file__).resolve().parents[3])/'atlas'
ROOTS = (ATLAS/'literature'/'poetics', ATLAS/'music'/'poetics')

LABELS = (('worldview', 'Картина мира'), ('reader', 'Читатель'), ('time', 'Время'),
          ('composition', 'Композиция'), ('narrator', 'Повествователь'), ('character', 'Персонаж'),
          ('language', 'Язык'), ('imagery', 'Образы'), ('themes', 'Темы'), ('devices', 'Приёмы'),
          ('genres', 'Жанры'), ('forbidden', 'Школа не делает'), ('markers', 'По чему узнаётся'),
          ('reading', 'Понятно и интересно — в этой школе это значит'))


@lru_cache(maxsize=None)
def load(school: str) -> dict | None:
    for root in ROOTS:
        path = root/f'{school}.yaml'
        if path.exists():
            return yaml.safe_load(path.read_text())
    return None


def flat(value) -> str:
    if isinstance(value, dict):
        return ' '.join(f'{flat(v)}' for v in value.values())
    if isinstance(value, list):
        return '; '.join(flat(v) for v in value)
    return str(value).strip()


MUSIC_LABELS = {'reader': 'Слушатель', 'narrator': 'Голос и исполнитель', 'character': 'Что здесь вместо героя',
                'language': 'Музыкальный язык', 'reading': 'Понятно и захватывает — в этой школе это значит'}


def labels(school: str):
    p = load(school) or {}
    if p.get('art') == 'music':
        return tuple((k, MUSIC_LABELS.get(k, label)) for k, label in LABELS)
    return LABELS


def manifesto(school: str) -> list[str]:
    p = load(school)
    return list(p.get('manifesto', [])) if p else []


def brief(school: str, rules: str = '') -> str:
    """A school in two lines, for choosing among schools."""
    p = load(school)
    if not p:
        return rules
    return f'{p["name"]}. {flat(p.get("worldview", ""))} Манифест: {" ".join(p.get("manifesto", [])[:3])}'


def full(school: str, rules: str = '', keys=None) -> str:
    """The whole poetics as words, for writing and for reading a draft."""
    p = load(school)
    if not p:
        return f'Форма: {rules}'
    wanted = keys or [k for k, _ in LABELS]
    lines = [f'Школа «{p["name"]}».']
    if p.get('manifesto') and (keys is None or 'manifesto' in keys):
        lines.append('Манифест: ' + ' '.join(p['manifesto']))
    lines += [f'{label}: {flat(p[k])}' for k, label in labels(school) if k in wanted and p.get(k)]
    if rules and (keys is None or 'form' in keys):
        lines.append(f'Форма, которую проверяет код: {rules}')
    return '\n'.join(lines)
