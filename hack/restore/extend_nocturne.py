"""Extend an existing series without changing any earlier work or result (pod only)."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import converter
from mnemosyne.music.render import note_events
from mnemosyne.weave import fountain, registry, school_series, schools, surface
from mnemosyne.weave import nocturne_dynamics
from music_e2e import save


def extend(previous, source, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    info = json.loads((previous/'series.json').read_text())
    for name in ('source.tar.zst', 'source.yaml', 'recipient.key', 'envelope.bin'):
        shutil.copy2(previous/name, output/name)
    # Independent copies: later rendering cannot mutate the earlier series.
    shutil.copytree(previous/'full', output/'full', ignore=shutil.ignore_patterns('.drafts'))
    key = X25519PrivateKey.from_private_bytes((output/'recipient.key').read_bytes())
    encoder = fountain.Encoder((output/'envelope.bin').read_bytes(), info['frame_bytes'], key)
    assert encoder.snapshot.hex() == info['snapshot']
    index = max(i for w in info['works'] for i in w['indices']) + 1
    dest = output/'full'/f'{len(info["works"]):03d}-nocturne'; dest.mkdir()
    shutil.copy2(source, dest/'composition.musicxml')
    original = surface.read(source)
    root = registry.mark(nocturne_dynamics.prepare(original), nocturne_dynamics.IDENTITY)
    woven = school_series.encode_many(root, [encoder.frame(index)], key)
    surface.write(woven, dest/'work.musicxml')
    assert registry.decode(dest/'work.musicxml', key).frame == [encoder.frame(index)]
    # Strip additions and demand exact XML-tree equality, including rests, slurs,
    # voices, repeats, tempo, articulations and all original dynamic directions.
    recovered = surface.read(dest/'work.musicxml')
    for measure in recovered.findall('./part/measure'):
        for d in list(measure.findall('direction')):
            if d.get('id', '').startswith(schools.PREFIX): measure.remove(d)
    identification = recovered.find('identification')
    misc = identification.find('miscellaneous')
    misc.remove(misc.find(f'miscellaneous-field[@name="{registry.FIELD}"]'))
    if not len(misc): identification.remove(misc)
    def tree(el):
        return (el.tag, sorted(el.attrib.items()), (el.text or '').strip(), [tree(c) for c in el])
    assert tree(recovered) == tree(original)
    scores = [converter.parse(p).toSoundingPitch() for p in (source, dest/'work.musicxml')]
    assert note_events(scores[0]) == note_events(scores[1])
    expanded = scores[0].expandRepeats()
    seconds = sum(float(b-a)*60/m.getQuarterBPM() for a,b,m in expanded.metronomeMarkBoundaries())
    deviations = [abs(float(sound.get('dynamics'))-(opts[0]+1.875)) for sound,opts in schools.slots(woven)]
    row = {'id':dest.name, 'school':'romantic', 'ensemble':'piano', 'seconds':seconds,
           'capacity':schools.capacity(woven), 'indices':[index], 'notes_unchanged':True,
           'original_xml_unchanged':True, 'knots':len(deviations),
           'max_deviation_points':max(deviations), 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    save(dest/'backup.json', row)
    save(dest/'method.json', {'decision':'Authorized bounded v2 micro-dynamics, no note/rest changes',
         'baseline':'Written dynamics; linear written hairpins, one 12-point step if no endpoint dynamic',
         'grid_quarters':0.5, 'levels':16, 'step_points':0.25, 'bound_points':1.875,
         'process_source':str(source), 'prior_series':str(previous)})
    info['works'].append(row)
    info['previous_series'] = str(previous)
    save(output/'series.json', info)
    print(json.dumps(row), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); extend(a.previous, a.source, a.out)
