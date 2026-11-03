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
    return [sorted((float(n.offset), float(n.quarterLength),
                    tuple(sorted(p.midi for p in n.pitches)))
                   for n in part.flatten().notes)
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



def render_score(score, plan, destination, soundfont):
    """Publish a school score only after XML, engraving and audio validation.

    Keep every attempt in .drafts; a nonempty destination is never overwritten.
    The sample conversion manifest and licence travel with the work.
    """
    from music21 import converter
    from .schools.common import analyze
    from .schools.performance import write_midi
    import numpy as np
    import xml.etree.ElementTree as ET

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (destination/'render.json').exists():
        raise FileExistsError(f'Already rendered: {destination}; select a new destination')
    if plan['ensemble'] == 'satb':
        # VSCO contains no choir: use an explicit, separately licensed GM profile.
        soundfont = FONT
        license_file = Path('/usr/share/doc/fluid-soundfont-gm/copyright')
        if not soundfont.is_file() or not license_file.is_file():
            raise FileNotFoundError('SATB requires fluid-soundfont-gm and its copyright notice')
        sample_info = {'library':'FluidR3_GM', 'license':'MIT',
            'sf2_sha256':hashlib.sha256(soundfont.read_bytes()).hexdigest(),
            'samples':[{'program':53,'low':0,'high':127,'lovel':0,'hivel':127}]}
    else:
        soundfont = Path(soundfont).resolve()
        sample_manifest = soundfont.parent/'manifest.json'
        license_file = soundfont.parent/'LICENSE'
        if not soundfont.is_file() or not sample_manifest.is_file():
            raise FileNotFoundError('Build the licensed sample bank with music.sample_bank first')
        sample_info = json.loads(sample_manifest.read_text())
        if hashlib.sha256(soundfont.read_bytes()).hexdigest() != sample_info['sf2_sha256']:
            raise ValueError('sample bank checksum mismatch')
    info = analyze(score,plan)
    # Ensure the chosen sample bank actually covers every played note/velocity.
    from music21 import dynamics
    for part in score.parts:
        program = part.recurse().getElementsByClass("Instrument").first().midiProgram
        if program==40 and plan['ensemble']=='string_orchestra':
            program=48
        for n in part.recurse().notes:
            d = n.getContextByClass(dynamics.Dynamic)
            velocity = max(20,min(110,round(127*(d.volumeScalar if d else .5))))
            if not any(z['program']==program and z['low']<=n.pitch.midi<=z['high'] and z['lovel']<=velocity<=z['hivel'] for z in sample_info['samples']):
                raise ValueError(f'Sample bank does not cover {part.id} MIDI {n.pitch.midi}, velocity {velocity}')
    (destination/'.drafts').mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='attempt-',dir=destination/'.drafts'))
    log = work/'render.log'
    (work/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    xml = work/'score.musicxml'
    score.write('musicxml',fp=str(xml))
    tree = ET.parse(xml)
    for identification in tree.findall('identification'):
        for creator in list(identification.findall('creator')):
            if creator.text=='Music21':
                identification.remove(creator)
    tree.write(xml,encoding='utf-8',xml_declaration=True)
    recovered = converter.parse(str(xml))
    # Some instruments are transposing; exported notation must round-trip to sound.
    recovered.toSoundingPitch(inPlace=True)
    if note_events(score.stripTies())!=note_events(recovered.stripTies()):
        raise RuntimeError('MusicXML round trip changed sounding events')
    analyze(recovered,plan)
    midi = work/'score.mid'
    write_midi(score,midi,plan['tempo'],plan['ensemble']=='string_orchestra')
    run(['musicxml2ly','-o',work/'score.ly',xml],log)
    run(['lilypond','-dno-point-and-click','-o',work/'score',work/'score.ly'],log)
    run(['fluidsynth','-ni','-o','synth.cpu-cores=1','-g','0.6','-R','1','-C','0',
         '-F',work/'score.wav','-r','44100',soundfont,midi],log)
    if any('error:' in line.lower() or 'failed to load' in line.lower() for line in log.read_text().splitlines()):
        raise RuntimeError(f'Renderer reported an error; see {log}')
    raw_audio = subprocess.check_output(['ffmpeg','-v','error','-i',str(work/'score.wav'),
        '-ac','1','-ar','44100','-f','f32le','-'])
    raw = np.frombuffer(raw_audio,dtype='<f4')
    raw_peak = float(np.max(np.abs(raw)))
    raw_rms = float(np.sqrt(np.mean(raw**2)))
    if raw_rms < 1e-9:
        raise RuntimeError('Silent sample render')
    # Raise quiet raw samples above loudnorm's absolute gating threshold first.
    pregain = min(.8/max(raw_peak,1e-9), .1/raw_rms)
    info['raw_rms'] = raw_rms
    info['pregain'] = pregain
    # Preserve the planned silence; allow a documented two-second reverb tail.
    run(['ffmpeg','-nostdin','-v','warning','-i',work/'score.wav','-af',
         f'volume={pregain},loudnorm=I=-20:TP=-2:LRA=12,apad','-t',str(plan['duration']+2),
         '-codec:a','libmp3lame','-q:a','2','-threads','1',work/'score.mp3'],log)
    audio = subprocess.check_output(['ffmpeg','-v','error','-i',str(work/'score.mp3'),
        '-ac','1','-ar','44100','-f','f32le','-'])
    data = np.frombuffer(audio,dtype='<f4')
    info.update(audio_seconds=len(data)/44100,tail_seconds=2,
                peak=float(np.max(np.abs(data))),rms=float(np.sqrt(np.mean(data**2))))
    if info['rms'] < .001 or info['peak'] >= 1 or abs(info['audio_seconds']-plan['duration']-2)>.1:
        raise RuntimeError(f'Audio validation failed: {info}')
    info['warnings'] = [l for l in log.read_text().splitlines() if not l.startswith('$') and ('warning' in l.lower() or 'error' in l.lower())]
    (work/'analysis.json').write_text(json.dumps(info,indent=2))
    shutil.copy2(Path(__file__).with_name('sample_libraries.yaml'),work/'sample_libraries.yaml')
    (work/'samples.json').write_text(json.dumps(sample_info,indent=2))
    shutil.copy2(license_file,work/'SAMPLE_LICENSE.txt')
    sources = list(Path(__file__).with_name('schools').glob('*.py')) + [Path(__file__),Path(__file__).with_name('sample_bank.py')]
    (work/'sources.json').write_text(json.dumps({str(p.relative_to(Path(__file__).parent)):p.read_text() for p in sources},indent=2))
    artifacts = ['sources.json','plan.json','score.musicxml','score.mid','score.ly','score.pdf','score.mp3',
                 'analysis.json','render.log','sample_libraries.yaml','samples.json','SAMPLE_LICENSE.txt']
    for filename in artifacts:
        path = work/filename
        if not path.exists() or not path.stat().st_size:
            raise RuntimeError(f'Missing artifact {path}')
    for filename in artifacts:
        shutil.copy2(work/filename,destination/filename)
    (destination/'render.json').write_text(json.dumps({'renderer_version':2,'draft':str(work),
        'python':sys.version,'music21':__import__('music21').__version__,
        'grammar_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).with_name('schools').glob('*.py')},
        'sample_sha256':sample_info['sf2_sha256'],'artifacts':{n:hashlib.sha256((work/n).read_bytes()).hexdigest() for n in artifacts}},indent=2))
    print(json.dumps({'school':plan['school'],**info}),flush=True)


if __name__ == '__main__':
    main()
