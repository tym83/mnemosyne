"""The atelier's life: continuous, in real time, one process per creator. There are no nights.

Every living creator works on their own: a work from idea to verdict, then rest as long as their
temper and strength ask, then the next work. Their own life (illness, despair, silence, death) is
the only thing that stops them. Fate runs on the real calendar: one creator is born, another dies,
each at their own time. Critics write when there is something released to read; the chronicle
writes when something happened. The sensor watches the cluster all the time, and every new
artifact — sketch, draft, margin, notebook, review, chapter — carries the pending backup at once.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import threading
import time
import traceback

from mnemosyne.lineage import Lineage, Parameters
from mnemosyne.music.composer import dump
from mnemosyne.operator.kube import connect, publish, snapshot, restored_lineage
from mnemosyne.operator.worker import LocalStudio, margins, sense

# Creators arrive one by one: an empty place is taken with this chance on a day.
BIRTH_RATE = .25
SENSE_EVERY = 900       # seconds between readings of the cluster
WORDS_EVERY = 600       # seconds between the critics' and chronicler's writing turns
MARGINS_PER_WORK = 4    # margin phrases a composer writes beside each work


def now():
    return datetime.now(timezone.utc)


def rest_seconds(artist, rng):
    """How long a creator rests after a work: their own temper and strength, not a timetable."""
    hours = rng.uniform(.5, 4) * (1.6 - artist.vitality) * (1.3 - .6 * artist.drive)
    return max(600., hours * 3600)


def start_delay(artist, rng):
    """Where in their rest a creator is when the atelier (re)starts."""
    return rng.uniform(0, rest_seconds(artist, rng))


def carrier_name(sketch, index, carrier):
    """A woven score's name, as the renderer looks it up: a movement by its number, a lone score by its sketch."""
    if 'movement_index' in carrier:
        return f"{sketch['id']}-mv{carrier['movement_index'] + 1}"
    return sketch['id'] if len(sketch.get('carriers') or [carrier]) == 1 else f"{sketch['id']}-{index}"


class Life:
    def __init__(self, request, base, key, api, namespace, *, night_factory=None, writer_factory=None):
        self.request, self.base, self.key, self.api, self.namespace = request, base, key, api, namespace
        self.lock = threading.RLock()       # the shared life and the ledger change under this lock
        self.checkpoint = base/'lineage.json'
        self.threads, self.stop = {}, threading.Event()
        self.night_factory, self.writer_factory = night_factory, writer_factory
        previous = (json.loads(self.checkpoint.read_text()) if self.checkpoint.exists()
                    else restored_lineage(api, namespace, request['atelier']) if api else None)
        if previous:
            self.life = Lineage.restore(previous)
        else:
            self.life = Lineage(request['atelier'], now(), parameters=Parameters(birth_rate=BIRTH_RATE, founders=1))
        self.objects = []
        self.log = base/'life.log'

    # -- shared state -------------------------------------------------------------------------
    def say(self, *words):
        with open(self.log, 'a') as out:
            out.write(f'{now().isoformat(timespec="seconds")} ' + ' '.join(map(str, words)) + '\n')

    def save(self):
        with self.lock:
            for _ in range(3):
                try:
                    dump(self.checkpoint, self.life.state())
                    return
                except RuntimeError:  # another creator changed their record while it was written
                    time.sleep(.2)

    def publish(self):
        if not self.api:
            return
        from mnemosyne.atelier import Atelier
        with self.lock:
            atelier = Atelier(self.life.cluster, self.base/'atelier')
            atelier.lineage(self.life)
            records = list({(o['kind'], o['metadata']['name']): o for o in atelier.objects}.values())
            for record in records:
                if record['kind'] == 'Atelier':
                    record['metadata']['name'] = self.request['atelier']
        try:
            publish(self.api, self.namespace, records, store=self.base)
        except Exception as exc:
            self.say('publish failed', type(exc).__name__, exc)

    def carry(self, sources=(), notebooks=(), folder=None):
        """Whatever was just made carries the pending pieces of the cluster's state now."""
        from mnemosyne.state.ledger import Ledger
        from mnemosyne.weave import night as texts, schools, surface
        from mnemosyne.weave.carry import carry
        folder = folder or self.base/'woven'
        with self.lock:
            extra = []
            entries, publish_texts = texts.texts(self.life, notebooks)
            if entries:
                extra.append((f'{self.life.cluster}-{now():%Y%m%dT%H%M%S}-texts', entries, 'variants', publish_texts))
            carriers = [(name, c, kind) for name, c, kind, _ in extra]
            carriers += [(name, schools.prepare(surface.read(path), school), school)
                         for name, path, school, *_ in sources]
            if not carriers:
                return None
            folder.mkdir(parents=True, exist_ok=True)
            report, _ = carry(Ledger(self.base/'ledger'), carriers, self.key, folder)
            for name, _, kind, publish_texts in extra:
                if name in report['carriers']:
                    publish_texts(json.loads((folder/(name + '.variants.json')).read_text()))
            dump(folder/f'carry-{now():%Y%m%dT%H%M%S%f}.json', report)
        self.say('carried', len(report['carriers']), 'carriers, pending', report['pending_pieces'])
        return report

    # -- the world: the cluster, fate, words ---------------------------------------------------
    def watch_cluster(self):
        from mnemosyne.state.ledger import Ledger
        while not self.stop.is_set():
            try:
                objects = snapshot(self.api, self.request['inventory'], self.request.get('snapshotNamespace'),
                                   self.request.get('includeSecrets', False))
                # The life of the whole cluster reaches the creators, unless the owner scoped it to one namespace.
                mood = sense(self.api, self.request.get('snapshotNamespace') or None, self.base)
                with self.lock:
                    self.mood = mood
                    ledger = Ledger(self.base/'ledger')
                    entry = ledger.observe(objects, now().isoformat(), self.key.public_key(),
                                           include_secrets=self.request.get('includeSecrets', False))
                    ledger.save()
                if entry:
                    self.say('cluster changed:', entry['kind'], entry['id'][:12])
            except Exception as exc:
                self.say('sensor failed', type(exc).__name__, exc)
            self.stop.wait(SENSE_EVERY)

    def fate(self):
        """One step of fate for each day of the calendar that has passed: ages, illnesses, births, deaths."""
        while not self.stop.is_set():
            with self.lock:
                due = (now() - datetime.fromisoformat(self.life.born)).days >= self.life.night
                if due:
                    self.life.step(getattr(self, 'mood', {}) or {})
                    self.say('day', self.life.night, 'working:', [a.id for a in self.life.working()])
            if due:
                self.save()
                self.publish()
            self.spawn()
            self.stop.wait(60)

    def words(self):
        """Critics review what was released; the chronicler writes what happened. When it is there."""
        while not self.stop.is_set():
            try:
                self.life.reception.write_words(life=self.life)
                self.life.write_words()
                self.carry(notebooks=())
                self.save()
            except Exception as exc:
                self.say('words failed', type(exc).__name__, exc)
            # The translator renders what was written in other tongues; the Lexicon follows what changed.
            try:
                from mnemosyne.writing.memory import backfill
                backfill(self.base, log=lambda *_: None)
            except Exception as exc:
                self.say('translation failed', type(exc).__name__, str(exc)[:200])
            try:
                from mnemosyne.lexicon import update
                with self.lock:   # the Lexicon reads a still copy of the life; creators go on meanwhile
                    still = Lineage.restore(json.loads(json.dumps(self.life.state())))
                update(still, self.base, limit=40)
            except Exception as exc:
                self.say('lexicon failed', type(exc).__name__, str(exc)[:200])
            self.stop.wait(WORDS_EVERY)

    # -- the creators --------------------------------------------------------------------------
    def spawn(self):
        with self.lock:
            living = {a.id for a in self.life.artists if a.status != 'dead'}
        for aid in living - {k for k, t in self.threads.items() if t.is_alive()}:
            thread = threading.Thread(target=self.creator, args=(aid,), name=aid, daemon=True)
            self.threads[aid] = thread
            thread.start()

    def artist(self, aid):
        return next(a for a in self.life.artists if a.id == aid)

    def creator(self, aid):
        """One creator's own life of work: a work, rest, the next work. Stops only with them."""
        rng = random.Random(f'{aid}:{now().isoformat()}')
        a = self.artist(aid)
        if not self.unfinished(a):
            # After a (re)start a creator is somewhere in their own rest, not at a common starting line.
            self.stop.wait(start_delay(a, rng))
        while not self.stop.is_set():
            a = self.artist(aid)
            if a.status == 'dead':
                return
            if a not in self.life.working():
                self.stop.wait(1800)   # ill, silent or in despair: their life, not ours, decides when
                continue
            budget = float(self.request.get('budget') or 0)
            if budget:
                from mnemosyne.models import spent_this_month
                if spent_this_month(self.base/'spend.jsonl') >= budget:
                    # The owner's monthly budget for the model API is spent: the creator waits for the next month.
                    self.say('budget reached', aid)
                    self.stop.wait(3600)
                    continue
            try:
                self.work(a)
            except Exception:
                self.say('work failed', aid, traceback.format_exc(limit=3).replace('\n', ' | '))
            self.save()
            self.publish()
            self.stop.wait(rest_seconds(a, rng))

    def unfinished(self, a):
        """A work the creator was in the middle of when the atelier stopped."""
        sessions = sorted((self.base/'creators'/a.id).glob('*/notebook.json'))
        if sessions:
            record = json.loads(sessions[-1].read_text())
            if record.get('status') == 'searching' and not record.get('error'):
                return sessions[-1].parent
        return None

    def unsounded(self, a):
        """An accepted work of this composer that has not sounded yet (it was accepted before it could)."""
        for notebook in sorted((self.base/'creators'/a.id).glob('*/notebook.json')):
            record = json.loads(notebook.read_text())
            if (record.get('status') == 'accepted' and record.get('final') and not record.get('sounding_work')
                    and 'sound' not in record):
                return notebook.parent
        return None

    def sound(self, a, folder):
        """Render an accepted work from its own session, as it would have sounded when it was accepted."""
        from mnemosyne.music.composer import Night
        record = json.loads((folder/'notebook.json').read_text())
        session = Night(self.life, a.id, folder, LocalStudio(), backend=None, sound=True, resume=True)
        session.record.clear()
        session.record.update(record)
        session.sketches[:] = record.get('sketches', [])
        session.record['sketches'] = session.sketches
        try:
            session.render_final(folder/'woven')
        except Exception as exc:
            session.record['sound'] = f'failed: {type(exc).__name__}: {str(exc)[:200]}'
            self.say('render failed', a.id, record.get('opus'), type(exc).__name__, str(exc)[:200])
        session.save()
        if session.record.get('sounding_work'):
            self.say('sounded', a.id, record.get('opus'))

    def work(self, a):
        if a.art == 'music' and self.night_factory is None and self.request.get('render', True):
            backlog = self.unsounded(a)
            if backlog:
                self.sound(a, backlog)
                return
        stamp = f'{now():%Y%m%dT%H%M%S}'
        root = self.base/'creators'/a.id/stamp
        if a.art == 'music':
            from mnemosyne.music.composer import Night
            resume = self.unfinished(a) if self.night_factory is None else None
            if resume:
                root = resume
                self.say('resuming', a.id, root.name)
            factory = self.night_factory or (lambda life, aid, folder: Night(
                life, aid, folder, LocalStudio(), backend=None, sound=self.request.get('render', True),
                resume=resume is not None))
            session = factory(self.life, a.id, root)
            self.say('composing', a.id, session.work_id)
            try:
                session.run('', drafts=self.request.get('drafts', 3), key=None)
            finally:
                sources = [(carrier_name(sk, i, c), session.root/c['score'],
                            'symphony' if sk.get('form') == 'symphony' else sk['plan']['school'],
                            {'plan': sk['plan'], 'form': sk.get('form', 'school')})
                           for sk in session.sketches if 'plan' in sk
                           for i, c in enumerate(sk.get('carriers') or [{'score': sk['score']}])]
                sources += margins(self.life, root, MARGINS_PER_WORK, only=a.id)
                self.carry(sources, [(session.work_id, session.record)], root/'woven')
                self.say('composed', a.id, session.record.get('status'))
            # An accepted work sounds from its woven scores; the backup never waits for it.
            try:
                session.render_final(root/'woven')
                if session.record.get('sounding_work'):
                    session.save()
                    self.say('sounded', a.id, session.work_id)
                elif session.record.get('sound_pending'):
                    self.say('not sounded', a.id, session.record['sound_pending'])
            except Exception as exc:
                self.say('render failed', a.id, type(exc).__name__, str(exc)[:200])
        else:
            from mnemosyne.writing.night import WriterNight
            resume = self.unfinished(a) if self.writer_factory is None else None
            if resume:
                root = resume
                self.say('resuming', a.id, root.name)
            factory = self.writer_factory or (lambda life, aid, folder: WriterNight(
                life, aid, folder, backend=None, resume=resume is not None))
            session = factory(self.life, a.id, root)
            self.say('writing', a.id, session.work_id)
            try:
                session.run()
            finally:
                from mnemosyne.writing.margins import page, writer_texts
                margin = {'margins': page(writer_texts(a, session.record), f'{a.id}:{root.name}')}
                notebooks = [(session.work_id, session.record)]
                if margin['margins']:
                    notebooks.append((f'{session.work_id}-margins', margin))
                self.carry((), notebooks, root/'woven')
                if margin['margins']:
                    dump(root/'margins.json', margin)
                self.say('wrote', a.id, session.record.get('status'))

    def run(self):
        threads = [threading.Thread(target=f, daemon=True, name=f.__name__)
                   for f in ((self.watch_cluster,) if self.api else ()) + (self.fate, self.words)]
        for t in threads:
            t.start()
        while not self.stop.is_set():
            self.stop.wait(60)


def main():
    os.umask(0o077)
    request = json.loads(os.environ['MNEMO_REQUEST'])
    request['atelier'] = os.environ['MNEMO_ATELIER']
    namespace = os.environ['MNEMO_NAMESPACE']
    base = Path('/works')/request['atelier']
    base.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MNEMO_SPEND_LOG', str(base/'spend.jsonl'))
    from .keys import load
    key = load(json.loads(Path(os.environ.get('MNEMO_KEY_CONFIG', '/runtime/key.json')).read_text()))
    with connect() as api:
        Life(request, base, key, api, namespace).run()


if __name__ == '__main__':
    main()
