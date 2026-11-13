"""The inner weather of one creator: the world as they take it, and their own life.

The same climate reaches everyone, and no one takes it the same way. Abundance
quiets one creator and makes another's grief louder; a steady world rests one
and stifles another; a world in loss can be shared pain or a reason to close
the door. How a creator takes the world depends on their temperament and on
what their own life has done to them: grief, despair, illness, need, solitude,
faith, recognition, a teacher's death, a student who went further.

The cluster's events never appear here; only qualities of the world, and the
creator's own biography, which is theirs to remember and to write from.
"""
from __future__ import annotations

import hashlib
import random

from .climate import feel, temperament
from .mood import words

STANCES = ('resonance', 'contrast', 'hunger', 'apart')


# A life before art: where a creator grew up, what fed them, what they love besides art, what turned them.
# Drawn once per creator, so the same quiet world reaches a pilot and a midwife as different stories.
PLACES = ('портовый город с доками и рыбным рынком', 'горная деревня, куда зимой не доходит автобус',
          'рудничный посёлок у отвалов', 'остров, где все знают расписание парома', 'окраина столицы у кольцевой дороги',
          'университетский город с монастырём на холме', 'степной разъезд у железной дороги', 'курортный городок вне сезона',
          'приграничный город, где говорят на двух языках', 'лесной посёлок при лесопилке', 'дельта реки с камышом и баржами',
          'старый квартал ремесленников в большом городе', 'военный городок, откуда семья переезжала каждые три года',
          'виноградная долина', 'северный город с полярной ночью', 'пригород у аэропорта')
TRADES = ('речной лоцман', 'акушерка', 'геодезист в экспедициях', 'судебный переводчик', 'повар в больничной столовой',
          'вальщик леса', 'учитель музыки в сельской школе', 'ветеринар', 'ночной таксист', 'архивист', 'мостостроитель',
          'цирковой акробат, потом униформист', 'рыбак на сейнере', 'аптекарь', 'диспетчер на сортировочной станции',
          'сиделка у стариков', 'реставратор икон', 'метеоролог на дальней станции', 'страховой агент', 'пожарный',
          'наборщик в типографии', 'садовник в ботаническом саду', 'боксёр, потом тренер', 'проводница дальних поездов')
LOVES = ('шахматы по переписке', 'горы и ночёвки на перевалах', 'голуби', 'звёздное небо и старый телескоп',
         'бокс', 'футбол на пустыре', 'грибы и тихий лес', 'опера с галёрки', 'старые карты', 'плавание в холодной воде',
         'карты Таро и пасьянсы', 'пчёлы', 'танго', 'охота с собакой', 'церковное пение', 'кино на последнем сеансе',
         'чужие письма с блошиного рынка', 'мотоциклы', 'лошади', 'кроссворды и словари')
TURNS = ('пожар в доме в девять лет', 'брат-близнец, с которым вы давно не говорите',
         'отец ушёл в море и не вернулся', 'долгая болезнь в юности и год в постели', 'первая любовь уехала в другую страну',
         'детство у бабушки, родители работали далеко', 'в двадцать лет — тюрьма за чужую вину',
         'война прошла через город твоего детства', 'найденный в детстве клад, о котором никто не знает', 'спасение незнакомцем на воде',
         'семья разорилась и переехала в одну комнату', 'годы чемпионства и одно поражение, после которого всё кончилось',
         'в тридцать лет — известие, что тебя усыновили', 'уход из монастыря', 'большая семья, младший из семерых детей',
         'младшая сестра, которую пришлось растить самому')


GENDER_WORDS = {'female': 'Ты — женщина.', 'male': 'Ты — мужчина.'}
# The creator's temper in art: comedy is as old as tragedy, and quiet sorrow is one temper among many.
TEMPERS = ('комический: смешное в людях и в себе, анекдот, розыгрыш, нелепость',
           'авантюрный: дорога, погоня, риск, сюжет, который тянет вперёд',
           'сатирический: злой глаз на власть, деньги, глупость',
           'гротескный: чудовищное и смешное вместе, преувеличение',
           'эпический: большие судьбы, поколения, войны, переселения',
           'романтический: страсть, бегство, высокое чувство, буря',
           'страшный: тайна, ужас, то, что за дверью',
           'фантастический: другие законы мира, чудо как правило',
           'трагический: судьба, вина, гибель, высокая цена',
           'лирический: свет, нежность, любовь, радость жизни',
           'философский: притча, парадокс, спор идей',
           'плутовской: ловкач, обман, весёлая безнравственность')


# The creator's own hand in language: a school sets the poetics, the hand is the person's.
SENTENCE = ('длинные периоды с придаточными, фраза на полстраницы', 'короткие рубленые фразы', 'фраза как разговор, '
            'с оговорками и перебивами', 'ритмическая, почти стиховая проза', 'сухой протокольный слог')
LEXICON = ('книжный, старинный словарь', 'просторечие и жаргон ремесла', 'точная терминология своего дела',
           'диалектные слова родных мест', 'простые слова, ни одного лишнего', 'пышная метафора, барочное изобилие')
VOICE = ('от первого лица, исповедально', 'от третьего лица, всевидящий рассказчик', 'от третьего лица, близко '
         'к одному герою', 'хор голосов и чужая речь', 'рассказчик-балагур, обращается к слушателю',
         'документ, письма, записи')
PACE = ('много диалога, сцены', 'почти без диалога, пересказ и картина', 'быстрый сюжет, событие за событием',
        'медленное время, подробность', 'монтаж обрывков')


def hand(a) -> str:
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:hand'.encode()).digest()[:8]))
    return (f'Твоя рука в языке: {r.choice(SENTENCE)}; {r.choice(LEXICON)}; {r.choice(VOICE)}; {r.choice(PACE)}. '
            'Школа задаёт поэтику, а рука твоя: держи её, если школа не требует иного.')


# The composer's own hand: a school sets the poetics, the hand in sound is the person's.
MELOS = ('длинная песенная мелодия на широком дыхании', 'короткие мотивы, которые дробятся и повторяются',
         'речитатив, мелодия как речь', 'мелодии почти нет: звук, тембр и поле', 'танцевальный мелос, ритм ведёт',
         'угловатая мелодия с широкими скачками', 'народный оборот, лад и подголосок')
HARMONY = ('ясная тональность и сильные каденции', 'модальность, старые лады, пустые квинты',
           'хроматика и блуждающие тяготения', 'кластеры и тесные созвучия', 'одно созвучие надолго, медленные сдвиги',
           'двенадцать тонов и серия', 'политональность, два мира разом')
TEXTURE = ('прозрачно: два-три голоса', 'густой оркестровый туман', 'хорал, аккорды столбами',
           'полифония, голоса спорят', 'мелодия и простой аккомпанемент', 'остинато, механика, моторика',
           'точки и паузы, пуантилизм')
SILENCE = ('тишина как материал, паузы долгие', 'почти без пауз, музыка не отпускает', 'обрывы и внезапные цезуры')
REPETITION = ('повтор — главная сила', 'не повторяет ничего дважды', 'возвращение изменённым', 'вариации без конца')
RHYTHM = ('метр как опора, ясная доля', 'смешанные и переменные размеры', 'свободное время без тактов',
          'танцевальные ритмы: вальс, марш, плясовая', 'медленное время, почти неподвижность', 'синкопы и сбитая доля')
TIMBRES = ('медные', 'деревянные духовые', 'струнные', 'ударные', 'арфа и челеста', 'фортепиано', 'хор', 'низкие басы',
           'высокие флажолеты', 'гитара и щипковые', 'орган')


def music_hand(a) -> str:
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:music-hand'.encode()).digest()[:8]))
    return (f'Твоя рука в звуке: {r.choice(MELOS)}; {r.choice(HARMONY)}; {r.choice(TEXTURE)}; {r.choice(SILENCE)}; '
            f'{r.choice(REPETITION)}; {r.choice(RHYTHM)}; любимые тембры: {", ".join(r.sample(TIMBRES, 2))}. '
            'Школа задаёт поэтику, а рука твоя: держи её, если школа не требует иного.')


def gender(a) -> str:
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:gender'.encode()).digest()[:8]))
    return 'female' if r.random() < .5 else 'male'


def temper(a, night: int | None = None) -> str:
    """Two leanings of this creator's temper; on some nights a third one comes over them."""
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:temper'.encode()).digest()[:8]))
    own = r.sample(TEMPERS, 2)
    if night is not None and _rng(a, night).random() < .25:
        own.append(_rng(a, night).choice(TEMPERS))
    return 'Твой нрав в искусстве: ' + '; '.join(own) + '.'


def origins(a) -> str:
    r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:origins'.encode()).digest()[:8]))
    return (f'{GENDER_WORDS[gender(a)]} Детство: {r.choice(PLACES)}. Ремесло, которым кормишься до искусства и рядом с ним: {r.choice(TRADES)}. '
            f'Любовь помимо искусства: {r.choice(LOVES)}. Что повернуло жизнь: {r.choice(TURNS)}. '
            'Это твой материал: люди, ремесло, места и слова этой жизни.')


def _rng(a, night):
    return random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:{night}'.encode()).digest()[:8]))


def pain(a) -> float:
    """How much the creator's own life hurts now."""
    ill = {'onset': .4, 'crisis': .8, 'prolonged': .6, 'changed': .2}.get(a.illness, .4) if a.illness else 0.
    return max(a.grief, a.despair, ill, 1 - a.health, a.isolation * .6, (1 - a.faith) * .7)


def stance(a, sensed: dict, night: int) -> str:
    """How this creator takes the world tonight: with it, against it, hungry for its opposite, or apart.

    A stable leaning from temperament, moved by the creator's own pain and by
    chance, so that the same creator can meet the same world differently.
    """
    lean = temperament(a.id + ':stance')
    bright = (sensed['abundance'] + sensed['steadiness'] + sensed['renewal']) / 3
    dark = (sensed['loss'] + sensed['scars'] + sensed['strain'] + sensed['turbulence']) / 4
    hurt = pain(a)
    weights = {
        'resonance': lean['steadiness'] * (a.openness + .3) * (1.2 - abs(bright - (1 - hurt))),
        'contrast': lean['scars'] * hurt * (bright + .2) * 1.6,
        'hunger': lean['novelty'] * (1 - hurt) * max(0., sensed['steadiness'] - sensed['turbulence'] + .3) * a.drive,
        'apart': lean['closedness'] * (a.solitude + a.isolation * .5 + .1) * (1 - dark * .5),
    }
    r = _rng(a, night)
    total = sum(weights.values()) or 1.
    pick, acc = r.random() * total, 0.
    for k in STANCES:
        acc += weights[k]
        if pick <= acc:
            return k
    return 'apart'


STANCE_WORDS = {
    ('resonance', 'bright'): 'Ты в ладу с миром: его покой и щедрость отзываются в тебе тем же.',
    ('resonance', 'dark'): 'Мир болит, и ты болишь вместе с ним: это общая беда, а не одиночество.',
    ('contrast', 'bright'): 'Вокруг сыто и спокойно, и от этого своя боль только громче. Её некуда деть, и её '
                            'хочется выплеснуть, даже если никто не хочет её слышать.',
    ('contrast', 'dark'): 'Все вокруг горюют, а ты закрываешься и упрямо держишь в себе другое: свет, злость или '
                          'смех, которых от тебя никто не ждёт.',
    ('hunger', 'bright'): 'Сытость и ровность душат. Тянет к краю, к буре, к тому, чего здесь нет.',
    ('hunger', 'dark'): 'Беды вокруг много, а ты голоден до неё: в ней ты наконец чувствуешь жизнь.',
    ('apart', 'bright'): 'Мир доходит до тебя глухо, как через стену. Ты живёшь своим.',
    ('apart', 'dark'): 'Что бы ни творилось вокруг, ты отгородился и слушаешь только себя.',
}


def memories(life, a, nights: int = 180) -> list[str]:
    """The creator's own life as they carry it: their biography, not the cluster's."""
    names = {b.id: ('' if b.name == b.id else b.name) for b in life.artists}
    since = life.night - nights
    out = []
    for e in life.events:
        if e['artist'] != a.id or e['night'] < since:
            continue
        f = e.get('facts') or {}
        k = e['kind']
        if k == 'bereavement':
            who = names.get(f.get('deceased'), '')
            relation = 'учитель' if f.get('deceased') in a.teachers else 'близкий тебе мастер'
            out.append(f'Умер {relation} {who}. ' + ('Горе ещё не отпустило.' if a.grief > .3 else 'Горе улеглось, но не ушло.'))
        elif k == 'illness_onset':
            out.append('Ты заболел.')
        elif k == 'illness_crisis':
            out.append('Болезнь была на краю, ты едва выкарабкался.')
        elif k == 'illness_recovery':
            out.append('Ты поправился' + (', но голос твой стал другим.' if f.get('altered_voice') else '.'))
        elif k == 'surpassed_by_student':
            out.append(f'Ученик {names.get(f.get("student"), "")} пошёл дальше тебя.')
        elif k == 'master':
            out.append('Тебя называют мастером.')
        elif k in ('silence', 'years_of_silence'):
            out.append('Ты долго молчал и не мог работать.')
        elif k == 'return':
            out.append('Ты вернулся к работе после молчания.')
    reviews = [r for r in life.reception.reviews if r['night'] >= since and
               any(w['id'] == r['work'] for w in a.catalogue)]
    harsh = [r for r in reviews if r['score'] < .35]
    warm = [r for r in reviews if r['score'] > .7]
    if harsh:
        out.append(f'Критик {harsh[-1]["lens"]["name"]} жёстко разнёс твою работу.')
    if warm:
        out.append(f'Критик {warm[-1]["lens"]["name"]} тебя понял и похвалил.')
    if a.catalogue and not reviews and len(a.catalogue) > 3 and a.recognition < .15:
        out.append('Твоих работ никто не замечает.')
    recent = [n for n in a.notebook if n.get('kind') == 'set_aside' and n.get('night', 0) >= since]
    if len(recent) >= 2:
        out.append('Замыслы один за другим не выдерживают твоего же суда.')
    state = [
        (a.despair > .45, 'Подступает отчаяние: зачем всё это.'),
        (a.isolation > .7, 'Ты очень одинок.'),
        (a.wealth < .2, 'Живёшь в нужде.'),
        (a.wealth > .85, 'Живёшь в достатке, и он тебя смущает.' if a.faith < .5 else 'Живёшь в достатке.'),
        (a.faith < .25, 'Вера в своё дело пошатнулась.'),
        (a.faith > .8, 'Ты твёрдо веришь в то, что делаешь.'),
        (a.recognition > .7, 'Тебя признали.'),
        (a.age > 365 * 3 and a.vitality < .4, 'Ты стар и устал.'),
        (a.health < .5 and not a.illness, 'Здоровье подводит.'),
        (a.illness == 'crisis', 'Ты тяжело болен.'),
    ]
    out += [text for cond, text in state if cond]
    return out


def inner(life, a) -> str:
    """Words for the creator's inner state tonight: the world as sensed, how it is taken, and their own life."""
    sensed = feel(life.climate, a.sensitivity or temperament(a.id))
    s = stance(a, sensed, life.night)
    bright = (sensed['abundance'] + sensed['steadiness'] + sensed['renewal']) / 3
    dark = (sensed['loss'] + sensed['scars'] + sensed['strain'] + sensed['turbulence']) / 4
    tone = 'bright' if bright >= dark else 'dark'
    lines = [origins(a), temper(a, life.night), 'Каким тебе кажется мир: ' + words(sensed, False, False), STANCE_WORDS[(s, tone)]]
    own = memories(life, a)
    if own:
        lines.append('Твоя собственная жизнь (это твоё, из этого можно писать): ' + ' '.join(own))
    return '\n'.join(lines)


def remembered(life, a, works: int = 3, chapters: int = 6) -> str:
    """The creator's memory of themselves: their last works as they wrote them, their diary, their Lives.

    A model has no memory between nights; the continuity of a life is what the
    creator carries into the next one.
    """
    from .weave.variants import plain
    parts = []
    done = [w for w in a.catalogue if not w.get('synthetic') and (w.get('excerpt') or w.get('idea'))][-works:]
    for w in done:
        head = f'«{w["title"]}»' if w.get('title') else 'работа'
        verdict = {'accept': 'ты её принял', 'rewrite': 'ты её не довёл'}.get(w.get('verdict'), '')
        line = f'{head}, ночь {w["night"]}' + (f', {verdict}' if verdict else '') + '.'
        if w.get('excerpt'):
            line += f' Начало: {w["excerpt"]}'
        elif w.get('idea'):
            line += f' Замысел: {plain(w["idea"])[:400]}'
        if w.get('diary'):
            line += f' В дневнике: {w["diary"]}'
        parts.append(line)
    lives = [c for c in life.biographies[a.id].chapters if c.get('text')][-chapters:] if a.id in life.biographies else []
    out = []
    if parts:
        out.append('Что ты написал последним (не повторяй, продолжай свой путь):\n' + '\n'.join(f'- {p}' for p in parts))
    if lives:
        out.append('Последнее в твоей биографии:\n' + '\n'.join(f'- {plain(c["text"])[:600]}' for c in lives))
    return '\n\n'.join(out)
