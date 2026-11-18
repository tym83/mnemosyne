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


# Russian past tense agrees with the creator: «родилась», «умер», «вернулись к работе».
FEMININE = {'Родился': 'Родилась', 'Впервые принял собственную работу': 'Впервые приняла собственную работу',
            'Закончил работу': 'Закончила работу', 'Умер': 'Умерла', 'Заболел': 'Заболела',
            'Поправился': 'Поправилась', 'Замолчал, перестал работать': 'Замолчала, перестала работать',
            'Вернулся к работе': 'Вернулась к работе', 'Признан мастером': 'Признана мастером',
            'Превзошёл учителя': 'Превзошла учителя', 'Пришёл в школу': 'Пришла в школу',
            'Вступил в школу': 'Вступила в школу', 'Основал школу': 'Основала школу',
            'Проверял озарение работой': 'Проверяла озарение работой',
            'принимал мир в лад с собой': 'принимала мир в лад с собой', 'жил наперекор миру': 'жила наперекор миру',
            'тосковал по буре': 'тосковала по буре', 'держался в стороне от мира': 'держалась в стороне от мира',
            'принял её': 'приняла её', 'не довёл её': 'не довела её', 'Ученик превзошёл его': 'Ученик превзошёл её',
            'О нём написали': 'О ней написали', 'Его работу открыли заново': 'Её работу открыли заново'}
def agree(text, a):
    from .psyche import gender
    g = gender(a)
    table = FEMININE if g == 'female' else {}
    for m, f in table.items():
        text = text.replace(m, f)
    return text


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
        if school in life.schools:
            return f'работа в школе «{life.schools[school]["name"]}»'
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
    return agree(f'{chapter.get("date", "")[:10]} — {what}. {detail}{tail}'.replace('  ', ' ').replace('. .', '.'), a)


def inner_at(life, a) -> dict:
    """The world as this creator sensed it at this moment and how they took it, kept beside the event."""
    from .climate import feel, temperament
    from .psyche import stance
    sensed = feel(life.climate, a.sensitivity or temperament(a.id))
    return {'stance': stance(a, sensed, life.night)}


KINDS_EN = {
    'birth': 'Born',
    'first_accepted': 'Accepted a work of their own for the first time',
    'writer_work': 'Finished a work',
    'composer_work': 'Finished a work',
    'last_work': 'Last work',
    'death': 'Died',
    'bereavement': 'Bereavement',
    'illness_onset': 'Fell ill',
    'illness_crisis': 'Crisis of the illness',
    'illness_prolonged': 'The illness dragged on',
    'illness_recovery': 'Recovered',
    'recovered': 'Recovered',
    'silence': 'Fell silent and stopped working',
    'years_of_silence': 'Years of silence',
    'return': 'Returned to work',
    'master': 'Recognised as a master',
    'surpassed': 'Surpassed their teacher',
    'surpassed_by_student': 'Surpassed by a student',
    'school': 'Came to a school',
    'joined_school': 'Joined a school',
    'school_birth': 'Founded a school',
    'period': 'A new period began',
    'rediscovery': 'Their work was rediscovered',
    'dream': 'A dream',
    'illumination': 'An illumination',
    'encounter': "An encounter with another's work",
    'verification': 'Tested an illumination in work',
    'secret_miracle': 'A secret miracle: a work that ended together with the life',
    'fertility': 'A fertile season',
    'review': 'A review',
    'essay': 'Written about',
}
STANCE_EN = {'resonance': 'they took the world in tune with themselves', 'contrast': 'they lived against the world',
             'hunger': 'they longed for a storm', 'apart': 'they kept apart from the world'}
CAUSE_EN = {'illness': 'illness', 'despair': 'despair', 'age': 'old age'}
ESSAY_EN = {'creator': 'an essay on the work', 'period': 'an essay on a period', 'obituary': 'an obituary',
            'manifesto': 'a reading of the manifesto', 'school': 'a survey of the school'}


def score_words_en(score):
    return 'rapturously' if score > .8 else 'approvingly' if score > .6 else \
        'with reserve' if score >= .4 else 'coldly' if score >= .2 else 'scathingly'


def line_en(life, a, chapter) -> str:
    """One dated line of the chronicle, in English."""
    from .psyche import gender
    names = {b.id: (b.name if b.name != b.id else 'a creator') for b in life.artists}
    f, kind = chapter.get('facts') or {}, chapter['kind']
    what = KINDS_EN.get(kind, kind.replace('_', ' ').capitalize())
    works = {w['id']: w for w in a.catalogue}
    def title(wid):
        w = works.get(wid, {})
        if w.get('title'):
            return f'“{w["title"]}”'
        school = w.get('school') or ''
        if school in life.schools:
            return f'a work in the school “{life.schools[school]["name"]}”'
        return f'a work in the school {school}' if school and 'tradition' not in school else 'a work outside the schools'
    detail = ''
    if kind == 'birth':
        teachers = [names.get(t, t) for t in a.teachers]
        detail = f'Art: {"music" if a.art == "music" else "literature"}. Teachers: {", ".join(teachers) or "none"}.'
    elif kind in ('writer_work', 'composer_work', 'first_accepted', 'last_work', 'rediscovery'):
        wid = f.get('work') or (chapter.get('works') or [None])[-1]
        verdict = {'accept': 'accepted it', 'rewrite': 'did not finish it'}.get(f.get('verdict'), '')
        detail = title(wid)[:1].upper() + title(wid)[1:] + (f'; {verdict}' if verdict else '') + '.'
        if kind == 'rediscovery' and f.get('posthumous'):
            detail += ' Posthumously.'
    elif kind == 'death':
        detail = f'Cause: {CAUSE_EN.get(f.get("cause"), f.get("cause") or "not recorded")}.'
    elif kind == 'bereavement':
        who = f.get('deceased')
        detail = f'Death of {"a teacher" if who in a.teachers else "a close master"}, {names.get(who, "")}.'
    elif kind in ('surpassed_by_student',):
        detail = f'Student: {names.get(f.get("student"), "")}.'
    elif kind == 'illness_recovery' and f.get('altered_voice'):
        detail = 'The voice had changed.'
    elif kind == 'school_birth':
        detail = f'The school “{f.get("name") or f.get("school") or ""}”.'
    elif kind == 'review':
        detail = f'The critic {f.get("critic")} wrote {score_words_en(f.get("score", .5))} about {title(f.get("work"))}.'
    elif kind == 'essay':
        detail = (f'The critic {f.get("critic")}, {ESSAY_EN.get(f.get("genre"), f.get("genre"))}; tone: '
                  f'{score_words_en(f.get("score", .5))}.')
    world = chapter.get('inner') or {}
    tail = f' In those days {STANCE_EN.get(world["stance"], world["stance"])}.' if world.get('stance') else ''
    text = f'{chapter.get("date", "")[:10]} — {what}. {detail}{tail}'.replace('  ', ' ').replace('. .', '.')
    g = gender(a)
    if g in ('female', 'male'):
        own, self_ = ('her', 'herself') if g == 'female' else ('his', 'himself')
        text = (text.replace('Their work', own.capitalize() + ' work').replace('their teacher', own + ' teacher')
                .replace('their own', own + ' own').replace('themselves', self_)
                .replace('In those days they', 'In those days ' + ('she' if g == 'female' else 'he')))
    return text
