"""Carry pending cluster-state pieces in tonight's works (shared by composer and operator)."""
import json
import xml.etree.ElementTree as ET

from . import catalogue, fountain, registry, school_series, surface


def carry(ledger, carriers, key, destination):
    """carriers: [(name, prepared_root, school)]. Writes woven MusicXML for carriers
    that received frames; returns the per-piece report. Every written frame is
    decoded back and validated against its catalogue before the ledger commits."""
    from . import schools
    capacities = [schools.capacity(root) - school_series.OVERHEAD for _, root, _ in carriers]
    plan = ledger.assign(capacities)
    encoders, written, batches = {}, [], []
    tonight = {}
    for (name, root, school), choice in zip(carriers, plan):
        if choice is not None:
            entry, first, count = choice
            span = tonight.setdefault(entry['id'], {'entry': entry, 'first': first, 'slots': []})
            span['slots'] += [(name, first + i) for i in range(count)]
    for span in tonight.values():
        entry = span['entry']
        encoders[entry['id']] = encoder = fountain.Encoder(ledger.envelope(entry), entry['frame_bytes'], key)
        span['catalogue'] = catalogue.create(encoder, [f'{n}/frame-{i}' for n, i in span['slots']],
                                             carrier_ids=[n for n, _ in span['slots']], first=span['first'])
    if tonight:
        destination.mkdir(parents=True, exist_ok=True)
    for (name, root, school), choice in zip(carriers, plan):
        if choice is None:
            continue
        entry, first, count = choice
        span, encoder = tonight[entry['id']], encoders[entry['id']]
        registry.mark(root, (school, 'dynamics-fountain', '2'))
        metadata = [{'carrier': name, **catalogue.metadata(span['catalogue'], i)} for i in range(first, first + count)]
        misc = root.find('./identification/miscellaneous')
        ET.SubElement(misc, 'miscellaneous-field', name='mnemosyne.catalogue').text = json.dumps(metadata)
        batch = [encoder.frame(i) for i in range(first, first + count)]
        path = destination/(name + '.musicxml')
        surface.write(school_series.encode_many(root, batch, key), path)
        decoded = registry.decode(path, key).frame
        if decoded != batch:
            raise RuntimeError('frame round trip mismatch')
        for frame, meta in zip(decoded, metadata, strict=True):
            catalogue.validate_work(frame, meta, key)
        (path.with_suffix('.catalogue.json')).write_text(json.dumps(metadata))
        written.append(name)
        batches.append(decoded)
    ledger.commit(plan)
    ledger.save()
    return {'carriers': written, 'frames': sum(len(b) for b in batches), 'frame_decode_verified': True,
            'pieces': [{k: p[k] for k in ('id', 'kind', 'at', 'k', 'carried', 'target', 'complete')}
                       for p in ledger.pieces],
            'pending_pieces': len(ledger.pending())}, batches
