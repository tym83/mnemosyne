"""Measured all-school XML round trips, tamper checks and surface statistics.

Run in a studio for the complete audit. No artist or language-model calls.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import random

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from music21 import converter
from scheherazade.music.schools import SCHOOLS
from scheherazade.music.render import note_events
from . import DecodeError, frames, fountain, payload, schools, surface

PLANS = Path(__file__).parents[1]/'music/schools/plans'


def plan_for(name):
    plan = json.loads((PLANS/f'{name}.json').read_text())
    # Keep section proportions to the nearest sixteenth, with exact total time.
    total_ticks = round(180*plan['tempo']/60*4)
    used = 0
    original = plan['duration']
    for i, sec in enumerate(plan['form']):
        ticks = total_ticks-used if i == len(plan['form'])-1 else round(total_ticks*sec['duration']/original)
        used += ticks
        sec['duration'] = ticks/4*60/plan['tempo']
    plan['duration'] = 180
    return plan


def distribution(values):
    counts = Counter(values)
    n = len(values)
    return {'counts':[counts[i] for i in range(16)], 'samples':n,
            'entropy_bits':-sum((c/n)*math.log2(c/n) for c in counts.values()),
            'mean_choice':sum(values)/n}


def rejected(fn):
    try:
        fn()
    except DecodeError:
        return True
    raise AssertionError('tampered score accepted')


def audit(out, trials=8):
    out.mkdir(parents=True, exist_ok=False)
    import sys
    import music21
    source_root = Path(__file__).parents[1]
    files = list(Path(__file__).parent.glob('*.py')) + list((source_root/'music/schools').glob('*.py'))
    (out/'sources.json').write_text(json.dumps({str(p.relative_to(source_root)):p.read_text() for p in files},indent=2))
    (out/'environment.json').write_text(json.dumps({'python':sys.version,'music21':music21.__version__},indent=2))
    key = X25519PrivateKey.generate()  # audit-only ephemeral key; never persisted
    rows = []
    for name, composer in sorted(SCHOOLS.items()):
        dest = out/name
        dest.mkdir()
        plan = plan_for(name)
        (dest/'plan.json').write_text(json.dumps(plan,indent=2))
        score = composer.compose(plan, plan['seed'])
        score.write('musicxml', fp=dest/'original.musicxml')
        original = surface.read(dest/'original.musicxml')
        root = schools.prepare(original, name)
        cap = schools.capacity(root)
        assert cap >= 32, (name, cap)
        surface.write(root, dest/'template.musicxml')
        root = surface.read(dest/'template.musicxml')
        wd, ud = [], []
        for trial in range(trials):
            data = os.urandom(cap*2)
            envelope = payload.seal(data, key.public_key(), context=frames.DOMAIN)
            woven = schools.weave_frame(root, envelope, 0, key)
            file = dest/f'woven-{trial}.musicxml'
            surface.write(woven, file)
            woven = surface.read(file)
            result = schools.read_frame(woven, key)
            assert result['data'] == envelope[:cap-frames.OVERHEAD]
            wd.extend(schools.digits(woven))
            plain = schools.unwoven(root, plan['seed']+trial)
            surface.write(plain, dest/f'unwoven-{trial}.musicxml')
            ud.extend(schools.digits(surface.read(dest/f'unwoven-{trial}.musicxml')))
        # Independent MusicXML parser: the original sounding notes are invariant.
        parsed = converter.parse(dest/'woven-0.musicxml').toSoundingPitch()
        assert note_events(parsed.stripTies()) == note_events(score.stripTies()), name
        tampered = deepcopy(woven)
        step = tampered.find('.//note/pitch/step')
        step.text = 'D' if step.text != 'D' else 'E'
        rejected(lambda: schools.read_frame(tampered, key))
        tampered = deepcopy(woven)
        snd, opts = schools.slots(tampered)[0]
        snd.set('dynamics', str(opts[(opts.index(float(snd.get('dynamics')))+1)%16]))
        rejected(lambda: schools.read_frame(tampered, key))
        tampered = deepcopy(woven)
        direction = next(d for d in tampered.iter('direction') if d.get('id','').startswith(schools.PREFIX))
        direction.find('offset').text = str(int(direction.findtext('offset'))+1)
        rejected(lambda: schools.read_frame(tampered, key))
        # Compact frame series, index/count and authenticated complete recovery.
        content = os.urandom(256)
        envelope = payload.seal(content, key.public_key(), context=frames.DOMAIN)
        count = math.ceil(len(envelope)/(cap-frames.OVERHEAD))
        recovered = []
        for i in range(count):
            file = dest/f'frame-{i}.musicxml'
            surface.write(schools.weave_frame(root,envelope,i,key), file)
            recovered.append(schools.read_frame(surface.read(file),key))
        assert frames.assemble(recovered,key) == content
        # Existing task-08 code; 30% whole-work erasure including systematic frames.
        envelope = payload.seal(content,key.public_key(),context=fountain.DOMAIN)
        encoder = fountain.Encoder(envelope, cap-12, key)
        n = fountain.recommended_count(len(envelope),cap-12)
        order = list(range(n)); random.Random(20261103).shuffle(order)
        survivors = sorted(order[math.ceil(n*.3):])
        recovered = []
        for i in survivors:
            file = dest/f'fountain-{i}.musicxml'
            surface.write(schools.weave_fountain(root,encoder,i,key),file)
            recovered.append(schools.read_fountain(surface.read(file),key))
        assert fountain.recover(recovered,key) == content
        a,b = distribution(wd),distribution(ud)
        tv = sum(abs(x/len(wd)-y/len(ud)) for x,y in zip(a['counts'],b['counts']))/2
        row = {'school':name,'seconds':180,'slots':len(schools.slots(root)),
               'bytes':cap,'frame_data_bytes':cap-frames.OVERHEAD,
               'fountain_data_bytes':cap-12-fountain.OVERHEAD,
               'frame_count':count,'fountain_k':encoder.k,'fountain_generated':n,
               'fountain_survived':len(survivors),'xml_roundtrip':True,'notes_unchanged':True,
               'tamper_checks':3,'woven':a,'unwoven':b,'total_variation':tv}
        rows.append(row)
        (dest/'results.json').write_text(json.dumps(row,indent=2))
        print(json.dumps({k:v for k,v in row.items() if k not in ('woven','unwoven')}),flush=True)
    (out/'measurements.json').write_text(json.dumps(rows,indent=2))
    lines = ['# Measured school surface capacity — v1', '',
             'All rows are actual 180-second MusicXML exports, not RNG entropy bounds.',
             'School plans and written/unwoven/woven XML are saved beside measurements.json.',
             'Section durations are rounded to the existing sixteenth grid; pitches, rests,',
             'articulations, note durations, row orders and methods are not changed by weaving.', '',
             'Each school declares FREE_CHANNELS next to its rules. The implemented channel',
             'has 16 equiprobable performance-dynamics levels, at most ±1.875 MusicXML',
             'dynamics percentage points from the prevailing level, on sounding spans only.',
             'Knots occur at onsets and each half-quarter inside sustained notation.',
             'Capacity is conditional on these plans, not a guarantee for silence or arbitrary short works.', '',
             '| School | Slots | Bytes / 3 min | Compact frame data | Fountain data¹ | XML / tamper | TV² |',
             '|---|---:|---:|---:|---:|---|---:|']
    for r in rows:
        lines.append(f"| {r['school']} | {r['slots']} | {r['bytes']} | {r['frame_data_bytes']} | {r['fountain_data_bytes']} | pass / 3 rejected | {r['total_variation']:.4f} |")
    lines += ['', '¹ Compact frame overhead: 20 bytes. Task-08 fountain overhead: 88 bytes',
              'plus 12 bytes binding the frame to the complete canonical work.',
              'Every school recovered a 256-byte payload through index/count frames and',
              'through the existing fountain code after 30% whole-work erasure.', '',
              f'² Total variation of the 16-choice histograms over {trials} woven and {trials} unwoven works.',
              'Full counts, mean choice and empirical entropy are in measurements.json.',
              'Encrypted data is random; frame headers and padding are structured. This is',
              'a descriptive comparison, not proof of statistical indistinguishability.', '',
              'Tamper tests change a pitch, one in-alphabet dynamic, and a knot offset.',
              'All fail authentication. A separate music21 parse confirms unchanged sounding',
              'pitch/onset/duration sequences. XML formatting whitespace is ignored by the MAC;',
              'arbitrary notation re-export is not promised to preserve authenticated context.', '',
              'The old raw-grammar entropy audit remains available in school_capacity.py.',
              'Discarded original RNG choices are not falsely counted as invertible channels.', '']
    (out/'CAPACITY.md').write_text('\n'.join(lines))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--trials',type=int,default=8)
    args = parser.parse_args()
    if args.trials < 1: parser.error('--trials must be positive')
    audit(args.out,args.trials)


if __name__ == '__main__':
    main()
