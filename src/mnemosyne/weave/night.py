"""Everything a night wrote that can carry: texts with variants and the audience log.

Scores are gathered by their producers. Here are the writings that belong to
the lineage itself: chapters of the Lives, critics' reviews, the composers'
notebooks, and the audience panel of the night. Anything drafted with
variants and not yet woven is gathered once; after weaving, the reading
replaces the draft and the draft stays as the apparatus.
"""
from . import audience, variants


def texts(life, notebooks=()):
    """One volume of tonight's unwoven drafts: (entries, publish)."""
    entries, targets = [], {}
    for review in life.reception.reviews:
        text = review.get('text')
        if isinstance(text, str) and not review.get('woven') and variants.places(text)[0]:
            key = f'/reviews/{review["id"]}'
            entries.append({'id': key, 'markup': text})
            targets[key] = review
    for aid, biography in sorted(life.biographies.items()):
        for i, chapter in enumerate(biography.chapters):
            text = chapter.get('text')
            if isinstance(text, str) and not chapter.get('woven') and variants.places(text)[0]:
                key = f'/lives/{aid}/{i}'
                entries.append({'id': key, 'markup': text})
                targets[key] = chapter
    for work, record in notebooks:
        for e in variants.collect({k: v for k, v in record.items() if k not in ('apparatus', 'backup')}):
            key = f'/notebooks/{work}{e["id"]}'
            entries.append({'id': key, 'markup': e['markup']})
            targets[key] = (record, e['id'])

    def publish(volume):
        for e in volume['entries']:
            target = targets[e['id']]
            if isinstance(target, tuple):
                record, path = target
                node, keys = record, path.strip('/').split('/')
                for k in keys[:-1]:
                    node = node[int(k)] if isinstance(node, list) else node[k]
                node[int(keys[-1]) if isinstance(node, list) else keys[-1]] = e['text']
                record.setdefault('apparatus', {})[path] = e['markup']
            else:
                target.update(text=e['text'], apparatus=e['markup'], woven=True)
    return entries, publish


def panel(life):
    """Tonight's audience log, if it is large enough to hold a frame."""
    from ..state.ledger import FRAME_BYTES
    for log in life.reception.logs:
        if log['night'] == life.night and audience.frame_capacity(log) >= FRAME_BYTES:
            def publish(woven, log=log):
                log.update(timestamps_ms=woven['timestamps_ms'], backup=woven['backup'], atelier=woven.get('atelier'))
            return log, publish
    return None, None
