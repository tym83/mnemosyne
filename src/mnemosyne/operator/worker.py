"""A studio Job: retain process, snapshot real API state, weave and verify."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from mnemosyne.atelier import Atelier, obj
from mnemosyne.lineage import Lineage
from mnemosyne.music.composer import dump
from mnemosyne.state.collect import archive
from mnemosyne.weave import catalogue, fountain, payload, registry, schools, school_series, surface
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


def weave(data, sources, destination, key, *, include_secrets=False):
    """One supplied score per work. Never pad capacity by inventing artistic works."""
    envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
    prepared = []
    for source in sources:
        name, path, school = source[:3]
        root = registry.mark(schools.prepare(surface.read(path), school), (school, 'dynamics-fountain', '2'))
        prepared.append((name, root))
    size = min(schools.capacity(r)-school_series.OVERHEAD for _, r in prepared)
    if size <= fountain.OVERHEAD:
        raise ValueError('approved scores have insufficient carrier capacity')
    encoder = fountain.Encoder(envelope, size, key)
    slots = [(name, root, (schools.capacity(root)-school_series.OVERHEAD)//size)
             for name, root in prepared]
    # Choose transport randomness, never musical content. Small fountain generations
    # can contain zero equations; retry sealing to obtain measured work-loss tolerance.
    from .loss import check
    for attempt in range(8):
        candidate_batches, offset = [], 0
        for _, _, count in slots:
            candidate_batches.append([encoder.frame(i) for i in range(offset, offset+count)])
            offset += count
        tolerance = check(candidate_batches, key)
        if tolerance['loss_tolerance_verified'] or attempt == 7 or offset < encoder.k:
            break
        envelope = payload.seal(data, key.public_key(), context=fountain.DOMAIN)
        encoder = fountain.Encoder(envelope, size, key)
    ids = [f'{name}-frame-{i}' for name, _, count in slots for i in range(count)]
    cat = catalogue.create(encoder, ids, carrier_ids=[name for name, _, count in slots for _ in range(count)])
    destination.mkdir()
    frames, batches, index = [], [], 0
    for name, root, count in slots:
        metadata = [catalogue.metadata(cat, i) for i in range(index, index+count)]
        misc = root.find('./identification/miscellaneous')
        ET.SubElement(misc, 'miscellaneous-field', name='mnemosyne.catalogue').text = json.dumps(metadata)
        batch = [encoder.frame(i) for i in range(index, index+count)]
        path = destination/(name+'.musicxml')
        surface.write(school_series.encode_many(root, batch, key), path)
        decoded = registry.decode(path, key).frame
        if decoded != batch:
            raise RuntimeError('frame round trip mismatch')
        for frame, meta in zip(decoded, metadata, strict=True):
            catalogue.validate_work(frame, meta, key)
        frames.extend(decoded)
        batches.append(decoded)
        index += count
    report = {'archive_sha256': hashlib.sha256(data).hexdigest(), 'archive_bytes': len(data),
              'frames': len(frames), 'required_source_frames': encoder.k,
              'frame_decode_verified': True, 'archive_recovered': False,
              'loss_tolerance_verified': False}
    try:
        recovered = fountain.recover(frames, key)
    except ValueError:
        report['phase'] = 'PendingCapacity'
    else:
        if recovered != data:
            raise RuntimeError('decoded archive mismatch')
        from mnemosyne.restore import recover_works
        if recover_works(destination, key, include_secrets=include_secrets)[0] != data:
            raise RuntimeError('restore disagrees with decode')
        report.update(archive_recovered=True, phase='Verified')
        from .loss import check
        report['loss'] = check(batches, key)
        report['loss_tolerance_verified'] = report['loss']['loss_tolerance_verified']
    dump(destination.parent/'decode.json', report)
    dump(destination.parent/'catalogue.json', cat)
    return report


def chamber(request, root):
    """Owner-authored commissions; the runtime makes no artistic judgments."""
    from mnemosyne.music.schools import SCHOOLS
    from mnemosyne.music.schools.plan import SchoolPlan
    from mnemosyne.music.schools.common import validate
    sources, records = [], []
    commissions = request.get('commissions', [])
    if not commissions:
        raise ValueError('chamber mode requires owner-authored idea, method and plan')
    for i, commission in enumerate(commissions):
        if not commission.get('idea') or not commission.get('method'):
            raise ValueError('commission needs an idea and method')
        plan = commission['plan']
        SchoolPlan.model_validate(plan)
        validate(plan)
        name = f'opus-{hashlib.sha256(root.name.encode()).hexdigest()[:12]}-{i:04d}'
        draft = root/name
        draft.mkdir()
        dump(draft/'commission.json', commission)
        score = SCHOOLS[plan['school']].compose(plan, plan['seed'])
        score.write('musicxml', fp=draft/'draft.musicxml')
        sources.append((name, draft/'draft.musicxml', plan['school'], {'plan': plan, 'form': 'school'}))
        records.extend([obj('Opus', name, {'art': 'music', 'title': plan['title'],
            'idea': commission['idea'], 'method': commission['method'], 'notebook': name,
            'artisticVerdict': 'owner-commission; not evaluated'}),
            obj('Notebook', name, {'opus': name, 'commission': commission, 'drafts': [name]}),
            obj('Sketch', name, {'opus': name, 'stage': 'draft', 'plan': plan})])
    return sources, records


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


def run(request, root, key, objects, *, previous=None):
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
    # The same resumable fate engine runs in every mode. Synthetic fate works remain
    # labelled synthetic; they are not counted as completed musical works.
    life.step(request.get('climate', {}))
    dump(root/'lineage.json', life.state())
    atelier = Atelier(life.cluster, root/'atelier')
    atelier.lineage(life)
    sources, records = [], []
    if request['mode'] == 'chamber':
        sources, records = chamber(request, root)
    else:
        from mnemosyne.music.composer import Night
        for artist in life.working():
            night = Night(life, artist.id, root/artist.id, LocalStudio(), backend=None)
            result = night.run(request.get('inner', 'Спокойствие'), drafts=request.get('drafts', 3), key=None)
            records.extend(o for o in night.objects if o['kind'] != 'Atelier')
            if result['status'] == 'failed':
                raise RuntimeError('composer failed; notebook retained')
            for sk in night.sketches:
                if 'plan' not in sk:
                    continue
                school = 'symphony' if sk.get('form') == 'symphony' else sk['plan']['school']
                for i, carrier in enumerate(sk.get('carriers') or [{'score': sk['score']}]):
                    sources.append((f'{sk["id"]}-{i}', night.root/carrier['score'], school,
                                    {'plan': sk['plan'], 'form': sk.get('form', 'school'),
                                     'movement_index': carrier.get('movement_index')}))
    dump(root/'lineage.json', life.state())
    # State does not enter artistic inputs. Capture scope is explicit in request.json.
    data = archive(objects, include_secrets=request.get('includeSecrets', False))
    report = weave(data, sources, root/'woven', key, include_secrets=request.get('includeSecrets', False)) if sources else {'phase': 'NoWork'}
    if request.get('render', False) and sources:
        for source in sources:
            name, original, _, rendering = source
            assignment_file = original.parent/'orchestration.json'
            rendering = {**rendering, 'action': 'woven',
                         'xml': (root/'woven'/(name+'.musicxml')).read_text(),
                         'assignment': json.loads(assignment_file.read_text()) if assignment_file.exists() else None}
            LocalStudio().run(rendering, root/'render'/name)
            registry.decode(root/'woven'/(name+'.musicxml'), key)
        report['post_render_decode_verified'] = True
        dump(root/'decode.json', report)
    for record in records:
        if record['kind'] == 'Opus':
            record['spec']['artifactDirectory'] = root.name
            files = list(record['spec'].get('files', []))
            for source in sources:
                name = source[0]
                if name.startswith(record['metadata']['name']):
                    files.append(atelier.store.put(root/'woven'/(name+'.musicxml')))
                    files.extend(atelier.store.put(p) for p in (root/'render'/name).rglob('*') if p.is_file())
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
    return records, report


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
        records, report = run(request, root, key, objects, previous=previous)
        publish(api, namespace, records)
        dump(checkpoint, json.loads((root/'lineage.json').read_text()))
        upload(root, storage)
    print(json.dumps({'directory': root.name, **report}))


if __name__ == '__main__':
    main()
