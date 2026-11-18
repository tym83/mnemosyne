"""Shared, seeded reception. Private merit never enters public review contexts.

Works and scores here are synthetic proxies, not artistic judgements. All
observers receive noisy, biased impressions. Words are an optional rendering.
"""
from __future__ import annotations
import math
import random
from copy import deepcopy

from pydantic import BaseModel
from .climate import temperament, feel, rhyme
from .writing.translator import FOREIGN_SCRIPT


def clip(x):
    return max(0., min(1., x))


WOMEN = {'Mira', 'Ada', 'Iris', 'Nora'}

class ReviewWords(BaseModel):
    text: str
    score: float | None = None  # the critic's own verdict after reading, 0..1


GENRE = {
    'work': 'Ты пишешь рецензию на вышедшую работу. Прочитай её и суди сам: по её школе и по своему вкусу.',
    'creator': 'Ты пишешь статью о творце в целом: его путь, работы, чего он ищет и чего достиг.',
    'period': 'Ты пишешь о новом периоде творца: что изменилось в его работах и почему это важно.',
    'obituary': 'Ты пишешь некролог: о жизни и работах умершего творца, честно, без лака.',
    'manifesto': 'Ты разбираешь манифест новой школы: что она обещает, с чем спорит, есть ли в ней будущее.',
    'school': 'Ты пишешь обзор школы: кто в ней работает, что она даёт сегодня, не выдохлась ли она.',
}
# A literary work is read as text: by its school's poetics, its genre, its language.
LITERARY = ('Ты пишешь литературно-критическую рецензию на вышедшую вещь. Прочитай текст целиком, как читатель '
            'её школы: суди её мерой поэтики этой школы — картина мира, время, композиция, повествователь, язык, '
            'приёмы, запреты, по чему школа узнаётся — и своим вкусом. Назови жанр и скажи, держит ли вещь его '
            'законы. Разбирай слово: синтаксис, ритм, интонацию, голос рассказчика, образы, композицию; цитируй '
            'строки текста (из оригинала, а если он не по-русски — с переводом). Написано ли это языком школы, или '
            'школа приложена к нейтральной прозе сверху? Не пересказывай сюжет вместо разбора.')

# Critics write about the arts they know; two write about both.
ARTS = {'laconic': ('literature',), 'polemical': ('music', 'literature'), 'lyrical': ('music',),
        'scholarly': ('literature',), 'ironic': ('music', 'literature'), 'intimate': ('music',)}
VOICE = {'laconic': 'лаконичный: коротко, точно, без украшений', 'polemical': 'полемист: спорит, ищет противника',
         'lyrical': 'лирик: пишет о том, что почувствовал', 'scholarly': 'учёный: традиция, приёмы, источники',
         'ironic': 'ироник: видит смешное и фальшивое', 'intimate': 'доверительный, как письмо близкому'}
TASTE = (('утешение и ясность', 'напряжение и неудобство'),
         ('сложное, пышное, многолюдное', 'простое и разреженное'),
         ('сдержанность', 'размах и бурю'),
         ('старые замкнутые формы и память традиции', 'новое, формы без памяти'))


def arts_of(critic):
    return critic.get('arts') or ARTS.get(critic.get('voice'), ('music', 'literature'))


class Reception:
    def __init__(self, seed):
        self.rng = random.Random(seed ^ 0xAC71)
        r = self.rng
        self.critics = [dict(id=f'critic-{i}', name=name, voice=voice,
                             values=[r.random() for _ in range(4)], schools={}, bias=r.uniform(-.3, .3),
                             reputation=r.uniform(.2, .9), fashion=r.random(), history=[])
                        for i, (name, voice) in enumerate(zip(
                            ['Mira', 'Leon', 'Ada', 'Pavel', 'Iris', 'Nora'],
                            ['laconic', 'polemical', 'lyrical', 'scholarly', 'ironic', 'intimate']))]
        self.segments = [dict(id=f'listeners-{i}', taste=[r.random() for _ in range(4)],
                              fashion=r.random(), word_of_mouth=r.random(), attachment=r.random())
                         for i in range(4)]
        for observer in self.critics + self.segments:
            observer['sensitivity'] = temperament(observer['id'])
        self.works = {}
        self.releases = []
        self.reviews = []
        self.logs = []
        self.fashion = [r.random() for _ in range(4)]
        self.queue = []  # critics' pieces promised and not yet printed

    def register(self, artist, work):
        if work['id'] in self.works:
            return
        self.works[work['id']] = dict(artist=artist.id, art=artist.art, feature=work['feature'], school=work['school'],
            private_merit=work['merit'], original_verdict=work['verdict'], night=work['night'],
            birth_climate=deepcopy(work.get('birth_climate', {})), publish_after=work.get('publish_after', work['night']),
            publicity=work.get('publicity', 'workshop'), synthetic=bool(work.get('synthetic')), released=False, attention=0., total=0, last=0, peak=0, curve=[], review_score=.5)
        if work['verdict'] == 'accept' and work.get('publish_after', work['night']) <= work['night']:
            self.release(work['id'], work['night'], 'publication', False)

    def release(self, wid, night, kind, posthumous):
        w = self.works[wid]
        if night < w.get('publish_after', 0):
            raise ValueError('publication embargo')
        event = dict(id=f'edition-{len(self.releases)}', work=wid, artist=w['artist'], night=night,
                     kind=kind, posthumous=posthumous, raw=kind == 'from_notebooks', curve=[], reviews=[])
        self.releases.append(event)
        w.update(released=True, attention=self.rng.uniform(.15, 1), last_release=night, edition=event['id'],
                 burst_seen=False)
        return event

    def review(self, wid, critic, night):
        w, r = self.works[wid], self.rng
        school = critic['schools'].setdefault(w['school'], r.uniform(-.4, .4))
        affinity = 1 - sum(abs(x-y) for x,y in zip(critic['values'], w['feature'])) / 4
        fashion = 1 - sum(abs(x-y) for x,y in zip(self.fashion, w['feature'])) / 4
        # A school everyone writes in tires the critics: the more it fills the season, the harder they judge it.
        season = [v for v in self.works.values() if v.get('art') == w.get('art') and night - v['night'] <= 120]
        share = sum(v['school'] == w['school'] for v in season) / max(1, len(season))
        fatigue = max(0., share - .3) * .6 * (.5 + critic['fashion']) if len(season) >= 4 else 0.
        score = clip(.45*w['private_merit'] + .3*affinity + school + critic['bias'] +
                     critic['fashion']*(fashion-.65) - fatigue + r.gauss(0, .25))
        previous = next((v for v in reversed(self.reviews) if v['work'] == wid and v['critic'] == critic['id']), None)
        revision = previous is not None and abs(score - previous['score']) > .3
        text = ''  # the critic's words come later, after reading
        row = dict(id=f'review-{len(self.reviews)}', kind='work', subject=wid, artist=w['artist'], work=wid,
                   night=night, critic=critic['id'],
                   edition=w['edition'], score=score, reputation=critic['reputation'], revision_of=previous['id'] if revision else None,
                   text=text, words_pending=True, carrier='literature', capacity_bytes=0,
                   lens=dict(name=critic['name'], voice=critic['voice'], values=critic['values'][:],
                             school_affinity=school, bias=critic['bias'], reputation=critic['reputation'],
                             mood=deepcopy(critic.get('mood', {}))))
        self.reviews.append(row)
        self.releases[int(w['edition'].split('-')[-1])]['reviews'].append(row['id'])
        w['review_score'] = score
        w['attention'] = min(2., w['attention'] + .15 * critic['reputation'])
        return row

    def interest(self, critic, w, author):
        return ((.5 + w['attention']) * (.5 + critic['reputation']) * (1 + critic['schools'].get(w['school'], 0))
                * (.6 + (author.recognition if author else 0)))

    def criticise(self, life, active, night):
        """Who writes what tonight: reviews of new editions, essays on creators, periods, schools, manifestos.

        A new edition draws several critics of its art within days, or nobody at all;
        a creator's turning points and new schools draw essays; the dead get obituaries.
        """
        r = self.rng
        artists = {a.id: a for a in life.artists}
        queue = self.__dict__.setdefault('queue', [])
        promised = {(q['kind'], q['subject'], q['critic']) for q in queue} | \
                   {(v.get('kind', 'work'), v.get('subject') or v['work'], v['critic']) for v in self.reviews}

        def promise(kind, subject, critic, artist, delay=None):
            if (kind, subject, critic['id']) in promised:
                return
            promised.add((kind, subject, critic['id']))
            queue.append(dict(due=night + (r.randint(0, 3) if delay is None else delay), kind=kind,
                              subject=subject, critic=critic['id'], artist=artist))

        for wid in active:
            w = self.works[wid]
            author = artists.get(w['artist'])
            for c in self.critics:
                if w.get('art', 'music') not in arts_of(c):
                    continue
                # A work written tonight is registered on the next night: its release is still news then.
                if night - w.get('last_release', -99) <= 1 and not w.get('burst_seen'):
                    chance = min(.95, .3 + .25 * self.interest(c, w, author)) * (.12 if w.get('synthetic') else 1)
                else:
                    chance = .0015 * self.interest(c, w, author)
                if r.random() < chance:
                    promise('work', wid, c, w['artist'])
        for wid in active:
            if night - self.works[wid].get('last_release', -99) >= 1:
                self.works[wid]['burst_seen'] = True
        for e in (e for e in life.events if e['night'] == night):
            a = artists.get(e['artist'])
            if a is None:
                continue
            kind = {'school_birth': 'manifesto', 'master': 'creator', 'return': 'creator', 'period': 'period',
                    'death': 'obituary', 'surpassed': 'creator'}.get(e['kind'])
            if kind is None or (kind != 'manifesto' and len(a.catalogue) < 3):
                continue
            chance = {'manifesto': .6, 'obituary': .5}.get(kind, .3)
            subject = (e['facts'].get('school') or e['facts'].get('name') or a.id) if kind == 'manifesto' else a.id
            for c in self.critics:
                if a.art in arts_of(c) and r.random() < chance * (.6 + a.recognition):
                    promise(kind, subject, c, a.id)
        if r.random() < .015:
            season = {}
            for w in self.works.values():
                if night - w['night'] <= 180 and not w.get('synthetic'):
                    season.setdefault((w.get('art') or 'music', w['school']), set()).add(w['artist'])
            schools = [k for k, who in season.items() if len(who) >= 2]
            if schools:
                art, school = r.choice(sorted(schools))
                critics = [c for c in self.critics if art in arts_of(c)]
                if critics:
                    promise('school', school, r.choice(critics), None, delay=0)
        due = sorted((q for q in queue if q['due'] <= night), key=lambda q: q['due'])[:4]
        for q in due:
            queue.remove(q)
            critic = next(c for c in self.critics if c['id'] == q['critic'])
            row = self.review(q['subject'], critic, night) if q['kind'] == 'work' else \
                self.essay(q['kind'], q['subject'], q['artist'], critic, night)
            author = artists.get(row.get('artist') or self.works.get(row.get('work') or '', {}).get('artist'))
            if author is None:
                continue
            life.event(author, 'review' if q['kind'] == 'work' else 'essay', critic=critic['name'],
                       work=row.get('work'), genre=q['kind'], score=round(row['score'], 2))
            if author.status != 'dead':
                if row['score'] < .3:
                    life._wound(author, life.p.despair_review * row['reputation'])
                elif row['score'] > .7:
                    author.despair *= .8

    def essay(self, kind, subject, artist, critic, night):
        """A critic's piece that is not about one edition: a creator, a period, a school, a manifesto, an obituary."""
        r = self.rng
        own = [w for w in self.works.values() if w['artist'] == artist] if artist else \
              [w for w in self.works.values() if w['school'] == subject]
        merit = sum(w['private_merit'] for w in own) / len(own) if own else .5
        school = critic['schools'].get(subject, 0) if kind in ('manifesto', 'school') else \
            sum(critic['schools'].get(w['school'], 0) for w in own) / max(1, len(own))
        score = clip(.45 * merit + .25 + school + critic['bias'] + r.gauss(0, .22))
        row = dict(id=f'review-{len(self.reviews)}', kind=kind, subject=subject, artist=artist, work=None,
                   night=night, critic=critic['id'], edition=None, score=score, reputation=critic['reputation'],
                   revision_of=None, text='', words_pending=True, carrier='literature', capacity_bytes=0,
                   lens=dict(name=critic['name'], voice=critic['voice'], values=critic['values'][:],
                             school_affinity=school, bias=critic['bias'], reputation=critic['reputation'],
                             mood=deepcopy(critic.get('mood', {}))))
        self.reviews.append(row)
        return row

    def step(self, life):
        r, night = self.rng, life.night
        artists = {a.id: a for a in life.artists}
        climate = getattr(life, 'climate', {})
        for observer in self.critics + self.segments:
            profile = observer.setdefault('sensitivity', temperament(observer['id']))
            q = feel(climate, profile)
            observer['mood'] = q
            key = 'values' if 'values' in observer else 'taste'
            # Comfort, intricate celebration, restraint, remembered closed forms.
            target = [1-q['strain'], clip(.5+(q['crowding']-.5)*profile['crowding_energy']),
                      1-q['turbulence'], clip(.5+.5*q['loss']-.5*q['renewal'])]
            observer[key] = [clip(x+.015*(y-x)) for x,y in zip(observer[key], target)]
            if key == 'values':
                observer['schools'] = {k: max(-.4, min(.4, v+.002*(q['loss']-q['renewal'])))
                                       for k,v in observer['schools'].items()}
                observer['bias'] = clip(.5 + observer['bias']*.98 - .01*q['turbulence'])-.5
        target = [sum(c['values'][i] for c in self.critics)/len(self.critics) for i in range(4)]
        self.fashion = [clip(x+.02*(y-x)) for x,y in zip(self.fashion, target)]
        for a in life.artists:
            for work in a.catalogue:
                self.register(a, work)
        for wid, work in self.works.items():
            if not work['released'] and work['original_verdict'] == 'accept' and night >= work.get('publish_after', 0):
                self.release(wid, night, 'publication', artists[work['artist']].status == 'dead')
        if r.random() < .015:
            self.fashion = [r.random() for _ in range(4)]
            c = r.choice(self.critics)
            c['values'] = [clip(x + c['fashion']*(y-x)) for x,y in zip(c['values'], self.fashion)]
            c['bias'] = r.uniform(-.3, .3)
            c['schools'] = {k: r.uniform(-.4, .4) for k in c['schools']}
            c['reputation'] = clip(c['reputation'] + r.gauss(0, .06))
            c['history'].append(dict(night=night, values=c['values'][:], bias=c['bias'], schools=c['schools'].copy()))
        # No quality gate: bad and good material can both return, at any age.
        if self.works and r.random() < life.p.discovery_rate:
            wid = r.choices(list(self.works), weights=[.2 + rhyme(climate, w.get('birth_climate')) for w in self.works.values()])[0]
            w = self.works[wid]
            a = artists[w['artist']]
            if night >= w.get('publish_after', 0) and night - w['night'] > life.p.discovery_age and (a.status == 'dead' or r.random() < .15) and r.random() < .2 + .8*rhyme(climate, w.get('birth_climate')):
                kind = 'rediscovery' if w['released'] else 'from_notebooks'
                event = self.release(wid, night, kind, a.status == 'dead')
                life.event(a, 'rediscovery', work=wid, edition=event['id'], posthumous=event['posthumous'],
                           from_notebooks=event['raw'])
                others = [b for b in life.working() if b.id != a.id]
                if others:
                    life.influence(a, r.choice(others), 'rediscovery', .6)
        active = [wid for wid,w in self.works.items() if w['released'] and w['attention'] > .002]
        self.criticise(life, active, night)
        counts = {}
        ratings = {}
        for wid in active:
            w = self.works[wid]
            count, impression = 0, 0.
            for s in self.segments:
                affinity = 1 - sum(abs(x-y) for x,y in zip(s['taste'], w['feature'])) / 4
                vogue = 1 - sum(abs(x-y) for x,y in zip(self.fashion, w['feature'])) / 4
                perceived = clip(.35*w['private_merit'] + .35*affinity + s['fashion']*(vogue-.6)
                                 + .2*w['review_score'] + r.gauss(0, .2))
                popularity = 1 + s['attachment']*math.log1p(w['total'])/5
                count += int(max(0, 35*w['attention']*perceived*popularity + r.gauss(0, 2)))
                impression += perceived / len(self.segments)
            counts[wid] = count
            ratings[wid] = round(impression, 2)
            w['total'] += count
            w['last'] = count
            w['peak'] = max(w['peak'], count)
            # Finite attention permits complete oblivion; word of mouth delays it.
            mouth = sum(s['word_of_mouth'] for s in self.segments)/len(self.segments)
            w['attention'] *= .955 + .025*mouth*impression
            if count:
                w['curve'].append([night, count])
                self.releases[int(w['edition'].split('-')[-1])]['curve'].append([night, count])
        fame, money = {}, {}
        for wid, count in counts.items():
            w = self.works[wid]
            aid = w['artist']
            fame[aid] = fame.get(aid, 0) + count*(.5 + w['review_score'])
            money[aid] = money.get(aid, 0) + count*.000002
        for a in life.artists:
            a.recognition = clip(a.recognition*.98 + .02*min(1, fame.get(a.id, 0)/200))
            if life.p.money_enabled:
                a.money_met = True
                a.wealth = clip(a.wealth + money.get(a.id, 0))
        chart = sorted(counts, key=lambda k: (-counts[k], k))
        # A fixed panel of 256 sampled listening timestamps, only if there is listening.
        programme = r.choices(chart, weights=[counts[k]+1 for k in chart], k=256) if sum(counts.values()) else []
        self.logs.append(dict(id=f'audience-{night}', night=night, counts=counts, ratings=ratings,
                              outcomes={a.id: [a.recognition, a.wealth] for a in life.artists},
                              editions={wid: self.works[wid]['edition'] for wid in counts},
                              chart=chart, programme=programme,
                              timestamps_ms=[i*337000 + r.randrange(256) for i in range(len(programme))]))

    @staticmethod
    def woman(critic):
        """The critics are four women and two men; Russian needs to know which, the names may not tell."""
        return critic.get('name') in WOMEN

    def critic_words(self, critic, life):
        """Who the critic is, in words: voice, taste, schools, mood, and what they wrote before."""
        values = critic['values']
        taste = [hi if v >= .5 else lo for v, (hi, lo) in zip(values, TASTE)]
        loves = [k for k, v in critic['schools'].items() if v > .15]
        hates = [k for k, v in critic['schools'].items() if v < -.15]
        she = self.woman(critic)
        lines = [f'Ты критик {critic["name"]}. Голос: {VOICE.get(critic["voice"], critic["voice"])}.',
                 'Ты женщина и пишешь о себе в женском роде.' if she else 'Ты мужчина и пишешь о себе в мужском роде.',
                 'Пишешь о ' + ' и '.join({'music': 'музыке', 'literature': 'литературе'}[x] for x in arts_of(critic)) + '.',
                 'В искусстве ценишь ' + '; '.join(taste) + '.',
                 'К авторам ты ' + ('щедр' if critic['bias'] > .15 else 'строг' if critic['bias'] < -.15 else 'справедлив') + ('а' if she else '') + '.']
        if loves:
            lines.append('Тебе близки школы: ' + ', '.join(loves) + '.')
        if hates:
            lines.append('Ты не любишь школы: ' + ', '.join(hates) + '.')
        if critic.get('mood'):
            from .mood import words
            lines.append('Твоё нынешнее настроение: ' + words(critic['mood'], False, False))
        before = [v for v in self.reviews if v['critic'] == critic['id'] and not v.get('words_pending')][-3:]
        if before:
            lines.append('Твои прежние рецензии (будь верен себе или скажи, что передумал):\n' + '\n'.join(
                f'- {v.get("about", "работа")}: {v["score"]:.1f}; {(v.get("text") or "")[:240]}' for v in before))
        return '\n'.join(lines)

    @staticmethod
    def work_words(author, work):
        from .weave.variants import plain
        name = author.name if author.name != author.id else 'автор'
        art = {'music': 'музыка', 'literature': 'литература'}.get(author.art, author.art)
        head = f'Автор: {name}. Искусство: {art}. Школа: {work.get("school")}.'
        if work.get('title'):
            head += f' Название: «{work["title"]}».'
        parts = [head]
        if work.get('idea'):
            parts.append('Замысел автора: ' + plain(work['idea'])[:1500])
        if work.get('text'):
            parts.append('Текст:\n\n' + work['text'][:12000])
            if work.get('translation'):
                parts.append('Перевод на русский:\n\n' + work['translation'][:12000])
        elif work.get('excerpt'):
            parts.append('Начало текста:\n\n' + work['excerpt'])
        if author.art == 'music':
            if work.get('concept'):
                parts.append('Замысел формы: ' + plain(work['concept'])[:800])
            if work.get('analysis'):
                parts.append('Что видно в партитуре: ' + '; '.join(f'{k}: {v}' for k, v in work['analysis'].items()))
            if work.get('synthetic'):
                parts.append('Это малая работа мастерской, эскиз в школе, без записанного замысла.')
        return '\n\n'.join(parts), (f'«{work["title"]}»' if work.get('title') else f'{name}, {work.get("school")}')

    @staticmethod
    def literary_words(author, work, life=None):
        """What a literary critic reads: the text itself, its language, its genre and its school's poetics."""
        from .lineage import LANGUAGE_NAMES
        from .weave.variants import plain
        from .writing import poetics
        from .writing.schools import SCHOOLS
        born = {}
        if life is not None:
            from .writing.founding import adopt
            born = adopt(life)
        key = work.get('school')
        school = SCHOOLS.get(key) or born.get(key)
        p = poetics.load(key) or {}
        name = author.name if author.name != author.id else 'автор'
        language = LANGUAGE_NAMES.get(author.language, author.language)
        kind = getattr(school, 'KIND', None) or p.get('kind')
        head = (f'Автор: {name}. Искусство: литература. Язык оригинала: {language}. '
                f'Школа: «{p.get("name", key)}» ({key}).')
        if kind:
            head += ' Род: ' + {'poetry': 'стихи', 'prose': 'проза'}.get(kind, kind) + '.'
        if p.get('genres'):
            head += ' Жанры школы: ' + poetics.flat(p['genres']) + '.'
        if work.get('title'):
            head += f' Название: «{work["title"]}».'
        parts = [head, 'Поэтика школы, мерой которой ты читаешь:\n' + poetics.full(key, getattr(school, 'RULES', ''))]
        if work.get('idea'):
            parts.append('Замысел автора (из его блокнота): ' + plain(work['idea'])[:1500])
        text = work.get('text') or work.get('excerpt')
        if text:
            parts.append(('Текст' if work.get('text') else 'Начало текста') + f' (оригинал, {language}):\n\n'
                         + plain(text)[:12000])
        if work.get('translation'):
            parts.append('Перевод на русский, сделанный Переводчиком (для понимания; судишь ты оригинал):\n\n'
                         + plain(work['translation'])[:12000])
        if work.get('diary'):
            parts.append('Дневник автора об этой вещи: ' + plain(work['diary'])[:400])
        return '\n\n'.join(parts), (f'«{work["title"]}»' if work.get('title') else f'{name}, {p.get("name", key)}')

    def essay_words(self, review, life):
        """What a critic reads before an essay: the creator's works and fortunes, a school, a manifesto."""
        from .weave.variants import plain
        kind, subject = review['kind'], review['subject']
        if kind in ('creator', 'period', 'obituary'):
            a = next(a for a in life.artists if a.id == review['artist'])
            name = a.name if a.name != a.id else 'творец'
            works = [w for w in a.catalogue if not w.get('synthetic')][-8:]
            lines = [f'Творец: {name}. Искусство: {"музыка" if a.art == "music" else "литература"}. '
                     f'Статус: {a.status}. Работ всего: {len(a.catalogue)}.']
            for w in works:
                got = [v for v in self.reviews if v.get('work') == w['id'] and v.get('text')]
                lines.append(f'- {("«" + w["title"] + "»") if w.get("title") else "работа"} ({w.get("school")}): '
                             + plain(w.get('idea') or '')[:300]
                             + (f' Начало: {w["excerpt"][:300]}' if w.get('excerpt') else '')
                             + (' Отзывы: ' + '; '.join(f'{v["lens"]["name"]} {v["score"]:.1f}' for v in got) if got else ''))
            chronicle = [c['text'] for c in life.biographies[a.id].chapters if c.get('text')][-12:]
            lines.append('Хроника жизни:\n' + '\n'.join(chronicle))
            return '\n'.join(lines), name
        if kind == 'manifesto':
            school = life.schools.get(subject) or next((s for s in life.schools.values() if s.get('name') == subject), {})
            items = school.get('manifesto', {}).get('manifesto', []) if school else []
            return (f'Новая школа «{school.get("name", subject)}». Манифест:\n' + '\n'.join(f'- {m}' for m in items),
                    f'манифест «{school.get("name", subject)}»')
        from .writing import poetics
        works = [(a, w) for a in life.artists for w in a.catalogue if w.get('school') == subject and not w.get('synthetic')][-8:]
        return (f'Школа «{(poetics.load(subject) or {}).get("name", subject)}». ' + poetics.brief(subject) + '\nРаботы:\n'
                + '\n'.join(f'- {(a.name if a.name != a.id else "творец")}: {w.get("title") or plain(w.get("idea") or "")[:200]}'
                             for a, w in works), f'школа {subject}')

    def write_words(self, writer_factory=None, life=None):
        if writer_factory is None:
            from .literature import Writer
            writer_factory = lambda nb: Writer(nb, role="critic", data_class="art")
        for review in self.reviews:
            if not review['words_pending']:
                continue
            critic = next((c for c in self.critics if c['id'] == review['critic']), None) or review['lens']
            prior = review['score']
            leaning = ('скорее понравится' if prior > .65 else 'скорее не понравится' if prior < .35 else 'неясно')
            author = work = None
            kind = review.get('kind', 'work')
            genre = GENRE.get(kind, GENRE['work'])
            if life is not None and review.get('work') in self.works:
                owner = self.works[review['work']]['artist']
                author = next((a for a in life.artists if a.id == owner), None)
                work = next((w for w in (author.catalogue if author else []) if w['id'] == review['work']), None)
            if kind != 'work' and life is not None:
                about, title = self.essay_words(review, life)
                system = self.critic_words(critic, life)
                author = next((a for a in life.artists if a.id == review.get('artist')), None)
            elif author and work is not None:
                if author.art == 'literature':
                    about, title = self.literary_words(author, work, life)
                    genre = LITERARY
                else:
                    about, title = self.work_words(author, work)
                system = self.critic_words(critic, life)
            else:  # no life at hand: only the public facts of the work
                about = (f'Школа: {self.works[review["work"]]["school"]}.' if review.get('work')
                         else f'{GENRE.get(kind, "")} Предмет: {review.get("subject")}.')
                title = 'работа' if review.get('work') else str(review.get('subject'))
                system = f'Ты критик {critic["name"]}. Голос: {VOICE.get(critic["voice"], critic["voice"])}.'
            nb = []
            she = isinstance(critic, dict) and self.woman(critic)
            prompt = (f'{about}\n\nДо чтения ты {"думала" if she else "думал"}: {leaning}. '
                      f'Прочитав, ты можешь передумать.'
                      + ('\nЭто пересмотр твоего прежнего мнения об этой работе.' if review.get('revision_of') else ''))
            instruction = (system + '\n' + genre + ' Говори о том, что действительно есть, цитируй и '
                'называй детали; не выдумывай того, чего нет. Не упоминай ночи, номера, мастерскую как механизм и '
                'технику. В score — твоя оценка от 0 до 1 после чтения.')
            words = writer_factory(nb).ask(instruction, prompt, ReviewWords, 'review:' + review['id'])
            if FOREIGN_SCRIPT.search(words.text):
                # A character of another script slipped into the Russian text: the critic writes it again.
                words = writer_factory(nb).ask(instruction, prompt + '\nПиши только по-русски, без иероглифов.',
                                               ReviewWords, 'review:' + review['id'] + ':again')
            review.update(text=words.text, words_pending=False, drafts=nb, about=title)
            if words.score is not None:
                score = clip(words.score)
                review.update(prior_score=prior, score=score)
                if review.get('work'):
                    self.works[review['work']]['review_score'] = score
                if author is not None and author.status != 'dead':
                    # The verdict changed on reading: the author lives with the one that was printed.
                    if prior < .3 <= score:
                        author.despair *= .85
                    elif score < .3 <= prior:
                        life._wound(author, life.p.despair_review * review['reputation'])

    def state(self):
        return deepcopy(dict(version=1, rng=self.rng.getstate(), critics=self.critics, segments=self.segments,
                             works=self.works, releases=self.releases, reviews=self.reviews, queue=self.queue,
                             logs=self.logs, fashion=self.fashion))

    @classmethod
    def restore(cls, data):
        if data['version'] != 1:
            raise ValueError('unsupported reception version')
        self = cls.__new__(cls)
        self.rng = random.Random()
        def tuples(x):
            return tuple(tuples(v) for v in x) if isinstance(x, (list, tuple)) else x
        self.rng.setstate(tuples(data['rng']))
        for k in ('critics', 'segments', 'works', 'releases', 'reviews', 'logs', 'fashion'):
            setattr(self, k, deepcopy(data[k]))
        self.queue = deepcopy(data.get('queue', []))
        return self
