"""Render completed NotaGen ABC/JSON pairs inside a studio pod.

    python -m scheherazade.music.render /work/gen/nocturne

FluidR3's grand piano is used for Keyboard prompts; orchestral scores keep
MusicXML instrument assignments. Originals, conversion warnings and drafts
are retained. A manifest written last marks a successful, reusable render.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

FONT = Path('/usr/share/sounds/sf2/FluidR3_GM.sf2')


def run(args, log):
    with log.open('a') as f:
        f.write('\n$ ' + ' '.join(map(str, args)) + '\n')
        f.flush()
        subprocess.run(list(map(str, args)), stdout=f, stderr=subprocess.STDOUT,
                       check=True, timeout=3600)


def diagnostics(score):
    """Structural warnings, not artistic judgments; implicit pickup is allowed."""
    from music21 import meter
    issues = []
    ends = []
    for pi, part in enumerate(score.parts, 1):
        measures = list(part.getElementsByClass('Measure'))
        ends.append({'part': pi, 'bars': len(measures), 'quarters': float(part.highestTime)})
        for mi, measure in enumerate(measures):
            ts = measure.timeSignature or measure.getContextByClass(meter.TimeSignature)
            if ts is None:
                continue
            expected = float(ts.barDuration.quarterLength)
            actual = float(measure.highestTime)
            pickup = mi == 0 and bool(measure.paddingLeft)
            if abs(actual - expected) > 1e-6 and not pickup:
                issues.append({'part': pi, 'bar': measure.number,
                               'kind': 'bar_length', 'quarters': actual, 'expected': expected})
            for voice in measure.voices:
                events = list(voice.notesAndRests)
                cursor = 0.0
                for event in events:
                    offset = float(event.offset)
                    if offset > cursor + 1e-6:
                        issues.append({'part': pi, 'bar': measure.number,
                                       'voice': str(voice.id), 'kind': 'voice_gap',
                                       'from': cursor, 'to': offset})
                    cursor = max(cursor, offset + float(event.quarterLength))
                if events and cursor < actual - 1e-6:
                    issues.append({'part': pi, 'bar': measure.number,
                                   'voice': str(voice.id), 'kind': 'voice_short',
                                   'quarters': cursor, 'bar_quarters': actual})
    return {'part_lengths': ends, 'unequal_part_lengths': len({p['quarters'] for p in ends}) > 1,
            'warnings': issues}


def note_events(score):
    return [sorted((float(n.getOffsetInHierarchy(part)), float(n.quarterLength),
                    tuple(sorted(p.midi for p in n.pitches)))
                   for n in part.recurse().notes)
            for part in score.parts]


def render(abc, out, piano_font, gm_font):
    from music21 import converter, instrument
    from . import analyze

    metadata = json.loads(abc.with_suffix('.json').read_text())
    keyboard = metadata.get('prompt', [''])[-1] == 'Keyboard'
    font = piano_font if keyboard else gm_font
    if not font.is_file():
        raise FileNotFoundError(font)
    digest = hashlib.sha256(abc.read_bytes() + abc.with_suffix('.json').read_bytes()).hexdigest()
    settings = {'source_sha256': digest, 'soundfont': str(font), 'renderer_version': 4}
    manifest = out / (abc.stem + '.render.json')
    suffixes = ('.abc', '.json', '.xml', '.pdf', '.mp3', '.mid', '.analysis.json')
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if all(old.get(k) == v for k, v in settings.items()) and all(
                (out / (abc.stem + ext)).is_file() and (out / (abc.stem + ext)).stat().st_size
                for ext in suffixes):
            print(f'skip {abc.name}', flush=True)
            return
    # Keep failed drafts too; publish only after all stages succeed.
    work = Path(tempfile.mkdtemp(prefix=abc.stem + '-', dir=out / '.drafts'))
    log = work / (abc.stem + '.render.log')
    source = work / abc.name
    shutil.copy2(abc, source)
    shutil.copy2(abc.with_suffix('.json'), source.with_suffix('.json'))
    xml = source.with_suffix('.xml')
    run([sys.executable, analyze.ABC2XML, '-o', work, source], log)
    score = converter.parse(str(xml))
    info = analyze.features(xml)
    info['structure'] = diagnostics(score)
    # Score.seconds can be NaN for multi-staff XML in music21. Integrate
    # explicit tempo regions instead, including beat units and MIDI repeats.
    def seconds(s):
        return sum(float(end - start) * 60 / mark.getQuarterBPM()
                   for start, end, mark in s.metronomeMarkBoundaries())

    info['score_seconds'] = seconds(score)
    info['playback_seconds'] = seconds(score.expandRepeats())
    info['tempo_default_qpm'] = 120 if info['bpm'] is None else None
    if keyboard:
        for part in score.parts:
            for ins in list(part.recurse().getElementsByClass(instrument.Instrument)):
                ins.activeSite.remove(ins)
            part.insert(0, instrument.Piano())
    midi = source.with_suffix('.mid')
    score.write('midi', fp=str(midi))
    # Direct abc2xml multi-voice XML makes musicxml2ly drop the upper staff
    # after a repeat. Round-trip its representation before engraving and
    # verify every sounding event survives, without changing the source XML.
    engraving = source.with_suffix('.engraving.musicxml')
    score.write('musicxml', fp=str(engraving))
    import xml.etree.ElementTree as ET
    tree = ET.parse(engraving)
    for identification in tree.findall('identification'):
        for creator in list(identification.findall('creator')):
            if creator.text == 'Music21':
                identification.remove(creator)
    tree.write(engraving, encoding='utf-8', xml_declaration=True)
    if note_events(score) != note_events(converter.parse(str(engraving))):
        raise RuntimeError('Engraving XML round-trip changed sounding events')
    ly = source.with_suffix('.ly')
    run(['musicxml2ly', '-o', ly, engraving], log)
    run(['lilypond', '-dno-point-and-click', '-o', work / abc.stem, ly], log)
    wav = source.with_suffix('.wav')
    run(['fluidsynth', '-ni', '-o', 'synth.cpu-cores=1', '-g', '0.5',
         '-F', wav, '-r', '44100', font, midi], log)
    run(['ffmpeg', '-nostdin', '-v', 'warning', '-threads', '1', '-i', wav,
         '-af', 'alimiter=limit=0.95:level=false', '-codec:a', 'libmp3lame',
         '-q:a', '2', '-threads', '1', source.with_suffix('.mp3')], log)
    probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                                    'format=duration', '-of', 'json', str(source.with_suffix('.mp3'))])
    info['audio_seconds'] = float(json.loads(probe)['format']['duration'])
    info['conversion_warnings'] = [line for line in log.read_text().splitlines()
                                   if any(term in line.lower() for term in
                                          ('warning:', 'converted to slur', 'error:'))]
    source.with_suffix('.analysis.json').write_text(json.dumps(info, indent=2, allow_nan=False))
    for ext in (*suffixes, '.engraving.musicxml', '.ly', '.render.log'):
        src = source.with_suffix(ext)
        if not src.is_file() or not src.stat().st_size:
            raise RuntimeError(f'Missing/empty artifact: {src}')
        shutil.copy2(src, out / src.name)
    temporary = manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps({**settings, 'draft': str(work)}, indent=2))
    temporary.replace(manifest)
    print(f'rendered {abc.name}: {info["key"]}, {info["bars"]} bars, '
          f'{info["score_seconds"]:.1f}s; {len(info["structure"]["warnings"])} structural warnings', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--out', type=Path, help='default: SOURCE/rendered')
    ap.add_argument('--piano-font', type=Path, default=FONT)
    ap.add_argument('--gm-font', type=Path, default=FONT)
    args = ap.parse_args()
    os.nice(19)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '1'
    subprocess.run(['ionice', '-c', '3', '-p', str(os.getpid())], check=True)
    out = (args.out or args.source / 'rendered').resolve()
    (out / '.drafts').mkdir(parents=True, exist_ok=True)
    import fcntl
    with (out / '.render.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        failed = 0
        for abc in sorted(args.source.resolve().glob('*.abc')):
            if not abc.with_suffix('.json').is_file():
                continue
            try:
                render(abc, out, args.piano_font, args.gm_font)
            except Exception as exc:
                failed += 1
                print(f'FAILED {abc.name}: {exc}; see {out}/.drafts', file=sys.stderr, flush=True)
        if failed:
            raise SystemExit(1)


if __name__ == '__main__':
    main()
