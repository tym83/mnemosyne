"""A studio Job: retain process, snapshot real API state, weave and verify."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import random
import os
from pathlib import Path
import uuid

from mnemosyne.atelier import Atelier, obj
from mnemosyne.lineage import Lineage
from mnemosyne.music.composer import dump
from mnemosyne.weave import registry, schools, surface
from mnemosyne.operator.kube import connect, publish, snapshot, restored_lineage


class LocalStudio:
    """Composer transport inside the scheduled studio; no nested kubectl or pods."""
    def run(self, request, destination):
        from mnemosyne.music.composer_worker import execute
        destination.mkdir(parents=True, exist_ok=False)
        dump(destination/'request.json', request)
        result = execute(request, destination/'result')
        dump(destination/'result/result.json', result)
        return result


def weave(objects, sources, root, key, *, include_secrets=False, at=None, extra=()):
    """Tonight's cluster state joins the ledger; tonight's works carry pending pieces.

    One supplied score per work. Never pad capacity by inventing artistic works."""
    from mnemosyne.state.ledger import Ledger
    from mnemosyne.weave.carry import carry
    ledger = Ledger(root.parent/'ledger')
    entry = ledger.observe(objects, at or datetime.now(timezone.utc).isoformat(), key.public_key(),
                           include_secrets=include_secrets)
    carriers = [(name, carrier, kind) for name, carrier, kind, _ in extra]
    carriers += [(name, schools.prepare(surface.read(path), school), school) for name, path, school, *_ in sources]
    report, _ = carry(ledger, carriers, key, root/'woven')
    suffix = {'variants': '.variants.json', 'audience': '.audience.json'}
    for name, _, kind, publish in extra:
        if name in report['carriers']:
            publish(json.loads((root/'woven'/(name + suffix[kind])).read_text()))
    report['observed'] = entry and {k: entry[k] for k in ('id', 'kind', 'at', 'k', 'target')}
    report['phase'] = 'Carrying' if report['pending_pieces'] else 'Verified'
    dump(root/'decode.json', report)
    return report


def choose_school(artist, work, schools):
    """The artist's own choice, seeded by the work: their school when they have
    one, otherwise drawn towards traditions they have not yet tried."""
    import random
    rng = random.Random(int.from_bytes(hashlib.sha256(work['id'].encode()).digest()[:8]))
    if artist.school in schools and rng.random() < .7:
        return artist.school
    used = {}
    for w in artist.catalogue:
        used[w.get('school')] = used.get(w.get('school'), 0) + 1
    names = sorted(schools)
    return rng.choices(names, weights=[1/(1+used.get(n, 0)) for n in names])[0]


def chamber(life, root):
    """Without models, the atelier still composes by itself: every work the
    artists' lives bring tonight, accepted or not, gets a real score from a
    school the artist chooses. Nobody outside the atelier supplies ideas."""
    from mnemosyne.music.schools import SCHOOLS
    plans = Path(__file__).parents[1]/'music/schools/plans'
    sources, records = [], []
    born = {k: v['plan'] for k, v in life.schools.items() if v.get('status') == 'accepted' and v.get('art', 'music') == 'music'}
    for a in (a for a in life.artists if a.art == 'music'):
        for work in (w for w in a.catalogue if w['night'] == life.night):
            school = choose_school(a, work, [s for s in SCHOOLS if (plans/f'{s}.json').exists() or s in born])
            plan = deepcopy(born[school]) if school in born else json.loads((plans/f'{school}.json').read_text())
            plan['school'] = school
            plan['seed'] = int.from_bytes(hashlib.sha256(work['id'].encode()).digest()[:4], 'big')
            plan['title'] = f'{a.name} — {work["id"]}'
            work['school'] = school
            draft = root/work['id']
            draft.mkdir()
            score = SCHOOLS[school].compose(plan, plan['seed'])
            score.write('musicxml', fp=draft/'draft.musicxml')
            sources.append((work['id'], draft/'draft.musicxml', school, {'plan': plan, 'form': 'school'}))
            records.extend([obj('Opus', work['id'], {'art': 'music', 'artist': a.id, 'title': plan['title'],
                'school': school, 'notebook': work['id'], 'kind': work['kind'],
                'artisticVerdict': work['verdict'], 'quality': work['quality']}),
                obj('Notebook', work['id'], {'opus': work['id'], 'process': work['process'],
                    'drafts': [work['id']]}),
                obj('Sketch', work['id'], {'opus': work['id'], 'stage': 'draft', 'plan': plan})])
    return sources, records


MARGINS = 4  # margin sketches per composer per day of life


def margins(life, root, per_creator=MARGINS, only=None):
    """The margins of every composer's notebook (avantext, §57.4): short phrases written by the
    rules of their home school, with no model, every night, whether or not tonight's work came off.
    They stay notes, never sound, and carry the backup in their performance dynamics."""
    from mnemosyne.music.schools import SCHOOLS
    plans = Path(__file__).parents[1]/'music/schools/plans'
    born = {k: v['plan'] for k, v in life.schools.items()
            if v.get('status') == 'accepted' and v.get('art', 'music') == 'music'}
    known = [s for s in SCHOOLS if (plans/f'{s}.json').exists() or s in born]
    sources, written = [], {}
    for a in (a for a in life.working() if a.art == 'music' and (only is None or a.id == only)):
        home = a.school if a.school in known else next(
            (w.get('school') for w in reversed(a.catalogue) if w.get('school') in known), None)
        if home is None:
            r = random.Random(int.from_bytes(hashlib.sha256(f'{a.id}:raised'.encode()).digest()[:8], 'big'))
            home = r.choice(sorted(known))
        folder = root/a.id/'margins'
        folder.mkdir(parents=True, exist_ok=True)
        for i in range(per_creator):
            plan = deepcopy(born[home]) if home in born else json.loads((plans/f'{home}.json').read_text())
            plan['school'] = home
            plan['seed'] = int.from_bytes(hashlib.sha256(f'{a.id}:{root.name}:margin:{i}'.encode()).digest()[:4], 'big')
            plan['title'] = f'{a.name} — поля тетради, {i+1}'
            path = folder/f'margin-{i:02d}.musicxml'
            SCHOOLS[home].compose(plan, plan['seed']).write('musicxml', fp=path)
            sources.append((f'{a.id}-{root.name}-margin-{i:02d}', path, home,
                            {'plan': plan, 'form': 'school', 'final': False}))
        written[a.id] = {'school': home, 'count': per_creator}
    dump(root/'margins.json', written)
    return sources


def upload(root, storage):
    if not storage.get('bucket'):
        return
    import boto3
    s3 = boto3.client('s3', endpoint_url=storage.get('endpoint') or None)
    prefix = storage.get('prefix', 'mnemosyne').strip('/') + '/' + root.name
    # Completion marker is uploaded last so incomplete uploads remain identifiable.
    paths = sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'complete.json')
    paths.append(root/'complete.json')
    for path in paths:
        s3.upload_file(str(path), storage['bucket'], prefix+'/'+path.relative_to(root).as_posix())


def run(request, root, key, objects, *, previous=None, climate=None):
    """climate comes only from the cluster sensor, never from the request."""
    root.mkdir(parents=True, exist_ok=False)
    dump(root/'request.json', request)
    if request['mode'] != 'chamber':
        from mnemosyne.models import Models
        endpoints = [e for role in ('artist', 'critic', 'chronicler', 'eye') for _, e in Models.load().route(role)]
        if not endpoints or any(e.location == 'dev' for e in endpoints):
            raise ValueError('production modes require configured cluster or API model endpoints')
        if request['mode'] in ('background', 'GPU') and any(e.location != 'cluster' for e in endpoints):
            raise ValueError('external model endpoints require explicit API mode')
    life = Lineage.restore(previous) if previous else Lineage(request['atelier'], datetime.now(timezone.utc))
    from mnemosyne.music.school_birth import register_all
    register_all(life.schools)
    # The same resumable fate engine runs in every mode. Synthetic fate works remain
    # labelled synthetic; they are not counted as completed musical works.
    life.step(climate or {})
    dump(root/'lineage.json', life.state())
    atelier = Atelier(life.cluster, root/'atelier')
    atelier.lineage(life)
    sources, records, notebooks, failures = [], [], [], []
    if request['mode'] == 'chamber':
        sources, records = chamber(life, root)
    else:
        from mnemosyne.music.composer import Night
        # Every creator works every day; only their own life (illness, despair, silence, renunciation)
        # takes them out of life.working() for a while.
        for artist in (a for a in life.working() if a.art == 'music'):
            night = Night(life, artist.id, root/artist.id, LocalStudio(), backend=None,
                          sound=request.get('render', True))
            # Inner life is the felt climate the composer derives itself; nothing is supplied.
            # One creator's failure is part of their night, kept in their notebook; the others go on.
            try:
                night.run('', drafts=request.get('drafts', 3), key=None)
            except Exception as exc:
                night.record.setdefault('error', f'{type(exc).__name__}: {exc}'[:500])
                night.record['status'] = 'failed'
                failures.append(artist.id)
            records.extend(o for o in night.objects if o['kind'] != 'Atelier')
            notebooks.append((night.work_id, night.record))
            for sk in night.sketches:
                if 'plan' not in sk:
                    continue
                school = 'symphony' if sk.get('form') == 'symphony' else sk['plan']['school']
                accepted = (night.record.get('verdict') or {}).get('verdict') == 'accept'
                for i, carrier in enumerate(sk.get('carriers') or [{'score': sk['score']}]):
                    sources.append((f'{sk["id"]}-{i}', night.root/carrier['score'], school,
                                    {'plan': sk['plan'], 'form': sk.get('form', 'school'),
                                     'movement_index': carrier.get('movement_index'), 'work': sk['id'],
                                     # Sketches and drafts stay notes; only the accepted work sounds.
                                     'final': accepted and sk['id'] == night.record.get('final')}))
    if request['mode'] != 'chamber':
        from mnemosyne.writing.night import WriterNight
        # Every creator works every day; only their own life (illness, despair, silence, renunciation)
        # takes them out of life.working() for a while.
        for artist in (a for a in life.working() if a.art == 'literature'):
            writer = WriterNight(life, artist.id, root/artist.id, backend=None)
            try:
                writer.run()
            except Exception as exc:
                writer.record.setdefault('error', f'{type(exc).__name__}: {exc}'[:500])
                writer.record['status'] = 'failed'
                failures.append(artist.id)
            notebooks.append((writer.work_id, writer.record))
    if request['mode'] != 'chamber':
        try:
            sources.extend(margins(life, root, request.get('margins', MARGINS)))
        except Exception as exc:
            failures.append(f'margins: {type(exc).__name__}: {exc}'[:300])
    if request['mode'] != 'chamber':
        try:
            life.reception.write_words(life=life)
            life.write_words()
        except Exception as exc:
            failures.append(f'words: {type(exc).__name__}: {exc}'[:300])
    from mnemosyne.weave import night as tonight
    extra = []
    entries, publish = tonight.texts(life, notebooks)
    if entries:
        extra.append((f'{request["atelier"]}-night-{life.night:05d}-texts', entries, 'variants', publish))
    log, publish_log = tonight.panel(life)
    if log is not None:
        extra.append((f'{request["atelier"]}-{log["id"]}', log, 'audience', publish_log))
    dump(root/'lineage.json', life.state())
    # State does not enter artistic inputs. Capture scope is explicit in request.json.
    report = weave(objects, sources, root, key, include_secrets=request.get('includeSecrets', False), extra=extra)
    dump(root/'lineage.json', life.state())
    if request.get('render', False) and sources:
        works = {}
        for name, original, _, rendering in sources:
            if rendering.get('final') is False:
                continue
            works.setdefault(rendering.get('work', name), []).append((name, original, rendering))

        def woven_of(name):
            return root/'woven'/(name+'.musicxml')

        def score_of(name, original):
            return (woven_of(name) if woven_of(name).exists() else original).read_text()

        for work, items in works.items():
            first = items[0][2]
            if first.get('form') == 'symphony':
                # A symphony sounds as one work: all its movements in one request.
                items.sort(key=lambda item: item[2].get('movement_index') or 0)
                job = {'action': 'woven', 'form': 'symphony', 'plan': first['plan'], 'born_schools': {},
                       'movements': [{'xml': score_of(n, o), 'plan': json.loads((o.parent/'plan.json').read_text()),
                                      'assignment': json.loads((o.parent/'orchestration.json').read_text())}
                                     for n, o, _ in items]}
            else:
                name, original, rendering = items[0]
                assignment_file = original.parent/'orchestration.json'
                job = {**rendering, 'action': 'woven', 'xml': score_of(name, original),
                       'assignment': json.loads(assignment_file.read_text()) if assignment_file.exists() else None}
                job.pop('final', None); job.pop('work', None)
            LocalStudio().run(job, root/'render'/work)
            for name, _, _ in items:
                if woven_of(name).exists():
                    registry.decode(woven_of(name), key)
        report['post_render_decode_verified'] = True
        dump(root/'decode.json', report)
    for record in records:
        if record['kind'] == 'Opus':
            record['spec']['artifactDirectory'] = root.name
            files = list(record['spec'].get('files', []))
            for source in sources:
                name = source[0]
                if name.startswith(record['metadata']['name']) and (root/'woven'/(name+'.musicxml')).exists():
                    files.append(atelier.store.put(root/'woven'/(name+'.musicxml')))
                    for folder in {root/'render'/name, root/'render'/name.rsplit('-', 1)[0]}:
                        files.extend(atelier.store.put(p) for p in folder.rglob('*') if p.is_file())
            record['spec']['files'] = files
            record['status'] = {'phase': report['phase'], 'backup': report}
    atelier.objects = []
    atelier.lineage(life)
    # Patch lineage fields without replacing the Atelier runtime configuration.
    records = list({(o['kind'], o['metadata']['name']): o
                    for o in [*atelier.objects, *records]}.values())
    for record in records:
        if record['kind'] == 'Atelier':
            record['metadata']['name'] = request['atelier']
    dump(root/'records.json', records)
    dump(root/'complete.json', report)
    report['failed_creators'] = failures
    return records, report


def sense(api, namespace, base):
    """Private sensor history beside the checkpoint; only qualities reach the artists."""
    from mnemosyne.mood import mood
    from mnemosyne.sensor import Sensor, incluster
    path = base/'sensor-private.json'
    history = json.loads(path.read_text()) if path.exists() else []
    history = (history + [Sensor(namespace, fetch=incluster(api)).read(history[-1] if history else None)])[-90:]
    dump(path, history)
    return mood(history)


def main():
    os.umask(0o077)
    request = json.loads(os.environ['MNEMO_REQUEST'])
    request['atelier'] = os.environ['MNEMO_ATELIER']
    namespace = os.environ['MNEMO_NAMESPACE']
    storage = json.loads(Path(os.environ['MNEMO_STORAGE']).read_text())
    base = Path('/works')/request['atelier']
    base.mkdir(parents=True, exist_ok=True)
    checkpoint = base/'lineage.json'
    root = base/(os.environ['MNEMO_NIGHT']+'-'+uuid.uuid4().hex[:12])
    from .keys import load
    key = load(json.loads(Path(os.environ.get('MNEMO_KEY_CONFIG', '/runtime/key.json')).read_text()))
    with connect() as api:
        objects = snapshot(api, request['inventory'], request.get('snapshotNamespace'),
                           request.get('includeSecrets', False))
        previous = (json.loads(checkpoint.read_text()) if checkpoint.exists()
                    else restored_lineage(api, namespace, request['atelier']))
        records, report = run(request, root, key, objects, previous=previous,
                              climate=sense(api, request.get('snapshotNamespace') or namespace, base))
        publish(api, namespace, records)
        dump(checkpoint, json.loads((root/'lineage.json').read_text()))
        if request['mode'] != 'chamber':
            # Translations are filled in after the night; a failure there never undoes the night.
            from mnemosyne.writing.memory import backfill
            try:
                backfill(base, log=lambda *_: None)
            except Exception as exc:
                report['translation_backfill'] = f'{type(exc).__name__}: {exc}'[:300]
                dump(root/'translation-backfill-error.json', {'error': report['translation_backfill']})
        upload(root, storage)
    print(json.dumps({'directory': root.name, **report}))


if __name__ == '__main__':
    main()
