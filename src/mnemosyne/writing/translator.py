"""The Translator: one figure outside the lineage, always the same, who renders everything into Russian.

He is not an artist: he is never born, never ages, has no fate, school or critic,
and takes no part in the story. He watches every night and translates what was
written in another language, so that a reader of the atelier can follow all of
it. Translations are kept beside the originals; the original is the work.
"""
import re

from pydantic import BaseModel

from ..literature import Writer
from ..weave.variants import plain

NAME = 'Переводчик'
SYSTEM = ('Ты — Переводчик. Ты один и всегда тот же, ты стоишь вне истории мастерской и только смотришь. '
          'Ты литературный переводчик русской школы: переводишь не слова, а текст, так, чтобы по-русски он '
          'читался как написанный по-русски, с той же интонацией, ритмом и плотностью, что в оригинале. '
          'Никаких калек и подстрочника: синтаксис и идиомы — русские, ремесленные слова — те, что сказал бы '
          'знающий человек. Сохраняй смысл, тон, недосказанность и форму: строки, строфы, размер и рифму там, '
          'где это возможно, заголовки, нумерацию и разметку. Ничего не добавляй от себя, не объясняй и не '
          'оценивай. Непереводимое оставь в оригинале и дай перевод в квадратных скобках.')


class Translation(BaseModel):
    text: str


def lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.strip()]


# Han, kana and hangul: a model's slip into another script, never Russian (unless the original has them).
FOREIGN_SCRIPT = re.compile('[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]')


def strays(original: str, translation: str) -> list[str]:
    return sorted(set(FOREIGN_SCRIPT.findall(translation)) - set(FOREIGN_SCRIPT.findall(original)))


def missing(original: str, translation: str) -> list[str]:
    """Form problems: the translation keeps every line of the original and slips into no other script."""
    a, b = len(lines(original)), len(lines(translation))
    problems = [] if a == b else [f'the original has {a} non-empty lines, the translation {b}; keep every line, one for one']
    stray = strays(original, translation)
    if stray:
        problems.append(f'the translation contains characters of another script: {"".join(stray)}; write them in Russian')
    return problems


def needed(language: str | None) -> bool:
    return bool(language) and language != 'ru'


def translate(text: str, language: str, notebook: list, *, backend=None, step='translate') -> str | None:
    """The Russian rendering of a reading text, or None when it is already Russian."""
    if not needed(language) or not text:
        return None
    from ..lineage import LANGUAGE_NAMES
    from ..literature import DRAFTING, LANGUAGE
    writer = Writer(notebook, backend=backend, role='translator', data_class='art')
    # The Translator writes Russian and never drafts variants: he is not one of the artists.
    drafting, spoken = DRAFTING.set(False), LANGUAGE.set(None)
    original = plain(text)
    name = LANGUAGE_NAMES.get(language)
    prompt = (f'Язык оригинала: {name}.\n\n' if name else '') + original
    try:
        result = writer.ask(SYSTEM, prompt, Translation, step).text
        for attempt in range(2):
            problems = missing(original, result)
            if not problems:
                break
            result = writer.ask(SYSTEM, f'{prompt}\n\nВ прошлом переводе ошибки: {problems}. '
                                f'Переведи заново, строка в строку, только по-русски.', Translation, f'{step}:retry{attempt}').text
        return result
    finally:
        LANGUAGE.reset(spoken)
        DRAFTING.reset(drafting)
