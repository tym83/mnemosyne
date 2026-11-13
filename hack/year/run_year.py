"""A year of one cluster's life, accelerated: music and literature together.

Every night: the cluster's real history (scenario ops) sets the climate; the
fate engine lives; every music work gets a chamber score; on scheduled nights
and occasions real writers' and composers' nights run with the configured
Writer (WRITER=claude uses the subscription CLI); the chronicler and critics
write; tonight's state of the cluster is woven into tonight's carriers.
Resumable: stop at any time, run again to continue. Run on the Mac (Writer CLI)
with composer studios on the workshop.

  WRITER=claude PYTHONPATH=src .venv/bin/python hack/year/run_year.py --out out/year/leonia
  PYTHONPATH=src .venv/bin/python hack/year/run_year.py --out out/year/leonia --restore-check
"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from mnemosyne.artist import inner_life
from mnemosyne.lineage import Lineage, Parameters
from mnemosyne.mood import mood
from mnemosyne.occasions import synthetic
from mnemosyne.operator.worker import chamber, weave
from mnemosyne.weave import night as tonight
from mnemosyne.weave.backup import write_new
from mnemosyne.weave.keys import WritingKey


class Replay:
    """The scenario's objects at a moment, read forward once."""
    def __init__(self, ops):
        self.lines, self.objects, self.pending = ops.open(), {}, None

    def at(self, moment):
        while True:
            o = self.pending or (json.loads(line) if (line := self.lines.readline()) else None)
            self.pending = None
            if o is None:
                return list(self.objects.values())
            if datetime.fromisoformat(o['at']) > moment:
                self.pending = o
                return list(self.objects.values())
            md = o['object']['metadata']
            k = (o['object']['apiVersion'], o['object']['kind'], md.get('namespace', ''), md['name'])
            if o['op'] == 'delete':
                self.objects.pop(k, None)
            else:
                self.objects[k] = o['object']


def keys(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name in ('owner.key', 'atelier.key'):
        if not (directory/name).exists():
            write_new(directory/name, X25519PrivateKey.generate().private_bytes_raw())
    owner = X25519PrivateKey.from_private_bytes((directory/'owner.key').read_bytes())
    atelier = X25519PrivateKey.from_private_bytes((directory/'atelier.key').read_bytes())
    return owner, WritingKey(atelier, owner.public_key())


def summary(life, night, extra):
    events = [e for e in life.events if e['night'] == night]
    return {'night': night, 'date': life.date(), 'climate': life.climate,
            'events': [[e['artist'], e['kind']] for e in events],
            'working': [[a.id, a.art, a.language, a.school] for a in life.working()], **extra}


def works_tonight(artist, night, every, seed):
    """Whether a creator sits down to work tonight: their own rhythm, moved by fertility and drive."""
    import hashlib
    import random
    r = random.Random(int.from_bytes(hashlib.sha256(f'{seed}:{night}:{artist.id}'.encode()).digest()[:8]))
    return r.random() < (1 / max(1., every)) * max(.3, 1 + artist.fertility) * (.5 + artist.drive)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cluster', default='leonia')
    ap.add_argument('--scenarios', type=Path, default=Path('out/scenarios'))
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--nights', type=int, default=365)
    ap.add_argument('--writer-every', type=float, default=28,
                    help='mean nights between one writer\'s nights; fertility and drive move it')
    ap.add_argument('--composer-every', type=float, default=45, help='the same for composers')
    ap.add_argument('--spaces', type=int, default=2, help='working creators per art')
    ap.add_argument('--birth-rate', type=float, default=1., help='chance a free space is taken on a night')
    ap.add_argument('--parallel', type=int, default=1, help='writer nights run at once')
    ap.add_argument('--pod', default='studio-1')
    ap.add_argument('--no-real', action='store_true', help='fate engine and chamber scores only')
    ap.add_argument('--no-words', action='store_true', help='skip chronicler and critics prose')
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--restore-check', action='store_true')
    a = ap.parse_args()
    owner, key = keys(a.out/'keys')
    if a.restore_check:
        return restore_check(a, owner)
    facts = json.loads((a.scenarios/a.cluster/'facts.json').read_text())
    start = datetime.fromisoformat(facts['start'])
    checkpoint = a.out/'lineage.json'
    life = Lineage.restore(json.loads(checkpoint.read_text())) if checkpoint.exists() else \
        Lineage(a.cluster, start, seed=a.seed, parameters=Parameters(spaces=a.spaces, birth_rate=a.birth_rate))
    replay = Replay(a.scenarios/a.cluster/'ops.jsonl')
    log = (a.out/'year.jsonl').open('a')
    backend = None if a.no_real else os.environ.get('WRITER')
    while life.night < a.nights:
        night = life.night + 1
        end = start + timedelta(days=night)
        occasions = synthetic(facts, end - timedelta(days=1), end, night)
        for request in occasions:
            life.schedule(request)
        life.step(mood(a.scenarios, a.cluster, end))
        root = a.out/'nights'/f'{night:03d}'
        if root.exists():
            import shutil
            shutil.rmtree(root)  # an interrupted night is redone from its checkpoint
        root.mkdir(parents=True)
        sources, records = chamber(life, root)
        notebooks, real = [], []
        inner = inner_life(a.scenarios, a.cluster, end)
        if backend:
            from concurrent.futures import ThreadPoolExecutor
            from mnemosyne.writing.night import WriterNight
            writers = [x for x in life.working() if x.art == 'literature' and works_tonight(x, night, a.writer_every, a.seed)]
            nights = [WriterNight(life, x.id, root/'writers'/x.id, backend=backend) for x in writers]

            def write(w):
                try:
                    w.run(inner)
                except Exception as exc:
                    w.record.setdefault('error', str(exc))
                return w
            with ThreadPoolExecutor(max(1, a.parallel)) as pool:
                for w in pool.map(write, nights):
                    notebooks.append((w.work_id, w.record))
                    real.append([w.artist.id, 'literature', w.record['status']])
        composers = [x for x in life.working() if x.art == 'music' and works_tonight(x, night, a.composer_every, a.seed)] \
            if backend else []
        for artist in composers:
            from mnemosyne.music.composer import Night, Studio
            if artist is not None:
                studio = Studio(root/'composers'/artist.id, a.pod)
                n = Night(life, artist.id, root/'composers'/artist.id, studio, backend=backend, sound=False)
                studio.setup()
                try:
                    n.run(inner, drafts=3, key=None)
                except Exception as exc:
                    n.record.setdefault('error', str(exc))
                notebooks.append((n.work_id, n.record))
                real.append([artist.id, 'music', n.record['status']])
                for sk in n.sketches:
                    if 'plan' in sk:
                        school = 'symphony' if sk.get('form') == 'symphony' else sk['plan']['school']
                        for i, c in enumerate(sk.get('carriers') or [{'score': sk['score']}]):
                            sources.append((f'{sk["id"]}-{i}', n.root/c['score'], school, {}))
        if backend and not a.no_words:
            try:
                life.reception.write_words(life=life)
                life.write_words()
            except Exception as exc:
                real.append(['words', 'error', str(exc)[:200]])
        extra = []
        entries, publish = tonight.texts(life, notebooks)
        if entries:
            extra.append((f'{a.cluster}-night-{night:05d}-texts', entries, 'variants', publish))
        panel, publish_panel = tonight.panel(life)
        if panel is not None:
            extra.append((f'{a.cluster}-{panel["id"]}', panel, 'audience', publish_panel))
        report = weave(replay.at(end), sources, root, key, at=end.isoformat(), extra=extra)
        checkpoint.write_text(json.dumps(life.state(), ensure_ascii=False))
        if backend and not a.no_words and real:
            # The Translator renders tonight's foreign words: ideas, titles, drafts, reviews.
            from mnemosyne.writing.memory import backfill
            try:
                backfill(a.out, log=lambda *_: None)
            except Exception as exc:
                real.append(['translate', 'error', str(exc)[:200]])
        log.write(json.dumps(summary(life, night, {
            'real': real, 'carriers': report['carriers'], 'frames': report['frames'],
            'observed': report['observed'], 'pending': report['pending_pieces']}), ensure_ascii=False) + '\n')
        log.flush()
        print(night, life.date()[:10], 'carriers', len(report['carriers']), 'pending', report['pending_pieces'],
              'real', real, flush=True)


def restore_check(a, owner):
    """Restore at the end of every month from all carriers, compare with the scenario."""
    from mnemosyne.restore import recover_works
    from mnemosyne.state.ledger import members, pack
    facts = json.loads((a.scenarios/a.cluster/'facts.json').read_text())
    start = datetime.fromisoformat(facts['start'])
    replay = Replay(a.scenarios/a.cluster/'ops.jsonl')
    results = []
    for month in range(1, 13):
        moment = start.replace(month=month % 12 + 1, year=start.year + month // 12) - timedelta(seconds=1)
        expected = replay.at(moment)
        try:
            data, objects, rep = recover_works(a.out/'nights', owner, at=moment.isoformat())
            got = rep['moment']['moment']
            same = data == pack(members(Replay(a.scenarios/a.cluster/'ops.jsonl').at(datetime.fromisoformat(got))))
            results.append({'asked': moment.isoformat(), 'restored_moment': got, 'objects': len(objects), 'identical': same})
        except ValueError as exc:
            results.append({'asked': moment.isoformat(), 'error': str(exc)[:200], 'expected_objects': len(expected)})
    (a.out/'restore-check.json').write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == '__main__':
    main()
