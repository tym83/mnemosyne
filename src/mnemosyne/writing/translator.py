"""The Translator: one figure outside the lineage, always the same, who renders everything into Russian.

He is not an artist: he is never born, never ages, has no fate, school or critic,
and takes no part in the story. He watches every night and translates what was
written in another language, so that a reader of the atelier can follow all of
it. Translations are kept beside the originals; the original is the work.
"""
from pydantic import BaseModel

from ..literature import Writer
from ..weave.variants import plain

NAME = 'Переводчик'
SYSTEM = ('Ты — Переводчик. Ты один и всегда тот же, ты стоишь вне истории мастерской и только смотришь. '
          'Переводи на русский язык точно и бережно, сохраняя форму: строки, строфы, размер и рифму там, где '
          'это возможно, заголовки, нумерацию, стрелки ссылок и разметку. Ничего не добавляй от себя, не '
          'объясняй и не оценивай. Непереводимое оставь в оригинале и дай перевод в квадратных скобках.')


class Translation(BaseModel):
    text: str


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
    try:
        return writer.ask(SYSTEM, f'Язык оригинала: {LANGUAGE_NAMES.get(language, language)}.\n\n{plain(text)}',
                          Translation, step).text
    finally:
        LANGUAGE.reset(spoken)
        DRAFTING.reset(drafting)
