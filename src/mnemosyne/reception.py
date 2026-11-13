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


def clip(x):
    return max(0., min(1., x))


class ReviewWords(BaseModel):
    text: str
    score: float | None = None  # the critic's own verdict after reading, 0..1


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
        w.update(released=True, attention=self.rng.uniform(.15, 1), last_release=night, edition=event['id'])
        return event

    def review(self, wid, critic, night):
        w, r = self.works[wid], self.rng
        school = critic['schools'].setdefault(w['school'], r.uniform(-.4, .4))
        affinity = 1 - sum(abs(x-y) for x,y in zip(critic['values'], w['feature'])) / 4
        fashion = 1 - sum(abs(x-y) for x,y in zip(self.fashion, w['feature'])) / 4
        score = clip(.45*w['private_merit'] + .3*affinity + school + critic['bias'] +
                     critic['fashion']*(fashion-.65) + r.gauss(0, .25))
        previous = next((v for v in reversed(self.reviews) if v['work'] == wid and v['critic'] == critic['id']), None)
        revision = previous is not None and abs(score - previous['score']) > .3
        text = (f"We were wrong about {wid}. " if revision else '') + (
            'A compelling work.' if score > .7 else 'An unconvincing work.' if score < .3 else 'A mixed impression.')
        row = dict(id=f'review-{len(self.reviews)}', work=wid, night=night, critic=critic['id'],
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
        # A new edition draws the critics of its art over the following weeks; older work, now and then.
        reviewed = {(v['work'], v['critic']) for v in self.reviews}
        candidates = []
        for wid in active:
            w = self.works[wid]
            fresh = night - w.get('last_release', w['night']) <= 21
            for c in self.critics:
                if w.get('art', 'music') not in arts_of(c) or (wid, c['id']) in reviewed:
                    continue
                interest = (.5 + w['attention']) * (.5 + c['reputation']) * (1 + c['schools'].get(w['school'], 0))
                if r.random() < (.05 if fresh else .002) * interest * (.4 if w.get('synthetic') else 1):
                    candidates.append((wid, c))
        for wid, c in candidates[:3]:
            row = self.review(wid, c, night)
            author = artists[self.works[row['work']]['artist']]
            if author.status != 'dead':
                if row['score'] < .3:
                    life._wound(author, life.p.despair_review * row['reputation'])
                elif row['score'] > .7:
                    author.despair *= .8
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

    def critic_words(self, critic, life):
        """Who the critic is, in words: voice, taste, schools, mood, and what they wrote before."""
        values = critic['values']
        taste = [hi if v >= .5 else lo for v, (hi, lo) in zip(values, TASTE)]
        loves = [k for k, v in critic['schools'].items() if v > .15]
        hates = [k for k, v in critic['schools'].items() if v < -.15]
        lines = [f'Ты критик {critic["name"]}. Голос: {VOICE.get(critic["voice"], critic["voice"])}.',
                 'Пишешь о ' + ' и '.join({'music': 'музыке', 'literature': 'литературе'}[x] for x in arts_of(critic)) + '.',
                 'В искусстве ценишь ' + '; '.join(taste) + '.',
                 'К авторам ты ' + ('щедр' if critic['bias'] > .15 else 'строг' if critic['bias'] < -.15 else 'справедлив') + '.']
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
            if life is not None:
                author = next((a for a in life.artists if a.id == self.works[review['work']]['artist']), None)
                work = next((w for w in (author.catalogue if author else []) if w['id'] == review['work']), None)
            if author and work is not None:
                about, title = self.work_words(author, work)
                system = self.critic_words(critic, life)
            else:  # no life at hand: only the public facts of the work
                about, title = f'Школа: {self.works[review["work"]]["school"]}.', 'работа'
                system = f'Ты критик {critic["name"]}. Голос: {VOICE.get(critic["voice"], critic["voice"])}.'
            nb = []
            words = writer_factory(nb).ask(
                system + '\nТы пишешь рецензию для читателей. Прочитай работу и суди её сам: по её школе и по '
                'своему вкусу. Говори о том, что в работе действительно есть, цитируй и называй детали; не '
                'выдумывай того, чего нет. Не упоминай ночи, номера, мастерскую как механизм и технику. '
                'В score — твоя оценка от 0 до 1 после чтения.',
                f'{about}\n\nДо чтения ты думал: {leaning}. Прочитав, ты можешь передумать.'
                + ('\nЭто пересмотр твоего прежнего мнения об этой работе.' if review.get('revision_of') else ''),
                ReviewWords, 'review:' + review['id'])
            review.update(text=words.text, words_pending=False, drafts=nb, about=title)
            if words.score is not None:
                score = clip(words.score)
                review.update(prior_score=prior, score=score)
                self.works[review['work']]['review_score'] = score
                if author is not None and author.status != 'dead':
                    # The verdict changed on reading: the author lives with the one that was printed.
                    if prior < .3 <= score:
                        author.despair *= .85
                    elif score < .3 <= prior:
                        life._wound(author, life.p.despair_review * review['reputation'])

    def state(self):
        return deepcopy(dict(version=1, rng=self.rng.getstate(), critics=self.critics, segments=self.segments,
                             works=self.works, releases=self.releases, reviews=self.reviews,
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
        return self
