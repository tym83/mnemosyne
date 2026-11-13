"""A creator's biography as a strict chronicle: what happened, when, and what the world was like for them.

Not a legend and not a novel. Every event of a creator's life is one dated
line, built from the facts the fate engine recorded, with the world as the
creator sensed it at that moment and how they took it. The creator's own
words (portrait, diary, letter, the image of an illumination) are kept apart.
"""
from __future__ import annotations

KINDS = {
    'birth': 'Родился',
    'first_accepted': 'Впервые принял собственную работу',
    'writer_work': 'Закончил работу',
    'composer_work': 'Закончил работу',
    'last_work': 'Последняя работа',
    'death': 'Умер',
    'bereavement': 'Утрата',
    'illness_onset': 'Заболел',
    'illness_crisis': 'Кризис болезни',
    'illness_prolonged': 'Болезнь затянулась',
    'illness_recovery': 'Поправился',
    'recovered': 'Поправился',
    'silence': 'Замолчал, перестал работать',
    'years_of_silence': 'Годы молчания',
    'return': 'Вернулся к работе',
    'master': 'Признан мастером',
    'surpassed': 'Превзошёл учителя',
    'surpassed_by_student': 'Ученик превзошёл его',
    'school': 'Пришёл в школу',
    'joined_school': 'Вступил в школу',
    'school_birth': 'Основал школу',
    'period': 'Начался новый период',
    'rediscovery': 'Его работу открыли заново',
    'dream': 'Сон',
    'illumination': 'Озарение',
    'encounter': 'Встреча с чужой работой',
    'verification': 'Проверял озарение работой',
    'secret_miracle': 'Тайное чудо: работа, закончившаяся вместе с жизнью',
    'fertility': 'Плодоносная пора',
    'review': 'Рецензия',
    'essay': 'О нём написали',
}
STANCE = {'resonance': 'принимал мир в лад с собой', 'contrast': 'жил наперекор миру',
          'hunger': 'тосковал по буре', 'apart': 'держался в стороне от мира'}
CAUSE = {'illness': 'болезнь', 'despair': 'отчаяние', 'age': 'старость'}
ESSAY = {'creator': 'статья о творчестве', 'period': 'статья о периоде', 'obituary': 'некролог',
         'manifesto': 'разбор манифеста', 'school': 'обзор школы'}


def score_words(score):
    return 'восторженно' if score > .8 else 'одобрительно' if score > .6 else \
        'сдержанно' if score >= .4 else 'холодно' if score >= .2 else 'разгромно'


def line(life, a, chapter) -> str:
    """One dated line of the chronicle."""
    names = {b.id: (b.name if b.name != b.id else 'творец') for b in life.artists}
    f, kind = chapter.get('facts') or {}, chapter['kind']
    what = KINDS.get(kind, kind.replace('_', ' '))
    works = {w['id']: w for w in a.catalogue}
    def title(wid):
        w = works.get(wid, {})
        if w.get('title'):
            return f'«{w["title"]}»'
        school = w.get('school') or ''
        # Fate-engine traditions carry identifiers, never names: they are 'outside the schools'.
        return f'работа в школе {school}' if school and 'tradition' not in school else 'работа вне школ'
    detail = ''
    if kind == 'birth':
        teachers = [names.get(t, t) for t in a.teachers]
        detail = (f'Искусство: {"музыка" if a.art == "music" else "литература"}. Учителя: '
                  f'{", ".join(teachers) or "нет"}.')
    elif kind in ('writer_work', 'composer_work', 'first_accepted', 'last_work', 'rediscovery'):
        wid = f.get('work') or (chapter.get('works') or [None])[-1]
        verdict = {'accept': 'принял её', 'rewrite': 'не довёл её'}.get(f.get('verdict'), '')
        detail = title(wid)[:1].upper() + title(wid)[1:] + (f'; {verdict}' if verdict else '') + '.'
        if kind == 'rediscovery' and f.get('posthumous'):
            detail += ' Посмертно.'
    elif kind == 'death':
        detail = f'Причина: {CAUSE.get(f.get("cause"), f.get("cause") or "не записана")}.'
    elif kind == 'bereavement':
        who = f.get('deceased')
        detail = f'Умер {"учитель" if who in a.teachers else "близкий мастер"} {names.get(who, "")}.'
    elif kind in ('surpassed_by_student',):
        detail = f'Ученик: {names.get(f.get("student"), "")}.'
    elif kind == 'illness_recovery' and f.get('altered_voice'):
        detail = 'Голос его стал другим.'
    elif kind == 'school_birth':
        detail = f'Школа «{f.get("name") or f.get("school") or ""}».'
    elif kind == 'review':
        detail = (f'Критик {f.get("critic")} {score_words(f.get("score", .5))} написал о '
                  f'{title(f.get("work"))}.')
    elif kind == 'essay':
        detail = (f'Критик {f.get("critic")}, {ESSAY.get(f.get("genre"), f.get("genre"))}; тон: '
                  f'{score_words(f.get("score", .5))}.')
    world = chapter.get('inner') or {}
    tail = ''
    if world.get('stance'):
        tail = f' В те дни {STANCE.get(world["stance"], world["stance"])}.'
    return f'{chapter.get("date", "")[:10]} — {what}. {detail}{tail}'.replace('  ', ' ').replace('. .', '.')


def inner_at(life, a) -> dict:
    """The world as this creator sensed it at this moment and how they took it, kept beside the event."""
    from .climate import feel, temperament
    from .psyche import stance
    sensed = feel(life.climate, a.sensitivity or temperament(a.id))
    return {'stance': stance(a, sensed, life.night)}
