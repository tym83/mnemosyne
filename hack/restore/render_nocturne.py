"""Pod-only piano preview: numeric sound dynamics, repeats and original engraving."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
import wave
from music21 import converter, dynamics, instrument, stream, tempo
from mnemosyne.music.render import note_events, run
from mnemosyne.weave import schools, surface
from mnemosyne.weave.nocturne_dynamics import timeline


def render(work, output_name='render'):
    dest = work/output_name; dest.mkdir(exist_ok=False)
    drafts = dest/'.drafts'; drafts.mkdir()
    log = dest/'render.log'
    root = surface.read(work/'work.musicxml')
    # Keep per-staff knots; MusicXML grand staff is split by music21.
    knots = {}
    for part in root.findall('part'):
        measure_starts = {}
        for measure, el, at, divisions in timeline(part):
            number = measure.get('number')
            measure_starts.setdefault(number, at)
            if el.tag == 'direction' and el.get('id','').startswith(schools.PREFIX):
                key = (number, el.findtext('staff', '1'))
                knots.setdefault(key, []).append((float(at-measure_starts[number]), float(el.find('sound').get('dynamics'))))
    source = converter.parse(work/'composition.musicxml')
    woven = converter.parse(work/'work.musicxml')
    assert note_events(source) == note_events(woven)
    expanded = woven.expandRepeats()
    boundaries = expanded.metronomeMarkBoundaries()
    def seconds(q):
        return sum(max(0, min(float(b),q)-float(a))*60/m.getQuarterBPM() for a,b,m in boundaries if q>float(a))
    audio = []
    for i, part in enumerate(expanded.parts):
        curve = []
        for measure in part.getElementsByClass('Measure'):
            for offset,value in knots.get((str(measure.number),str(i+1)), []):
                curve.append((seconds(float(measure.offset)+offset), value/63.0))
        if not curve: raise ValueError('missing staff automation')
        curve.sort()
        # Fixed MIDI attack, then continuous envelope from the actual woven XML.
        for d in list(part.recurse().getElementsByClass(dynamics.Dynamic)):
            d.activeSite.remove(d)
        for n in part.recurse().notes:
            n.volume.velocity = 80
            n.volume.velocityIsRelative = False
        for ins in list(part.recurse().getElementsByClass(instrument.Instrument)):
            ins.activeSite.remove(ins)
        part.insert(0,instrument.Piano())
        for mark in list(part.recurse().getElementsByClass(tempo.MetronomeMark)):
            mark.activeSite.remove(mark)
        for begin, end, mark in boundaries:
            part.insert(begin, tempo.MetronomeMark(number=mark.getQuarterBPM()))
        score = stream.Score(); score.insert(0,part)
        midi = drafts/f'staff-{i}.mid'; score.write('midi',fp=midi)
        wav = drafts/f'staff-{i}.wav'
        run(['fluidsynth','-ni','-o','synth.cpu-cores=1','-g','0.5','-F',wav,'-r','44100',
             '/usr/share/sounds/sf2/FluidR3_GM.sf2',midi], log)
        with wave.open(str(wav), 'rb') as audio_file:
            if audio_file.getsampwidth() != 2: raise ValueError('expected PCM16')
            rate = audio_file.getframerate()
            samples = np.frombuffer(audio_file.readframes(audio_file.getnframes()),dtype='<i2').reshape(-1,audio_file.getnchannels()).astype(float)/32768
        gain = np.interp(np.arange(len(samples))/rate, [t for t,v in curve], [v for t,v in curve])
        audio.append(samples*gain[:,None])
        (dest/f'staff-{i}-curve.json').write_text(json.dumps(curve))
    mix = np.zeros((max(map(len,audio)),2))
    for samples in audio: mix[:len(samples)] += samples
    peak = float(np.max(np.abs(mix)))
    scale = min(1,0.90/max(peak,1e-9)); mix *= scale
    with wave.open(str(drafts/'mix.wav'), 'wb') as audio_file:
        audio_file.setnchannels(2); audio_file.setsampwidth(2); audio_file.setframerate(44100)
        audio_file.writeframes((mix*32767).astype('<i2').tobytes())
    run(['ffmpeg','-nostdin','-v','warning','-threads','1','-i',drafts/'mix.wav','-codec:a','libmp3lame','-q:a','2',dest/'score.mp3'],log)
    # Original readable notation; numeric knots are performance-only.
    engraving = dest/'score.musicxml'; source.write('musicxml',fp=engraving)
    assert note_events(converter.parse(engraving)) == note_events(source)
    run(['musicxml2ly','-o',dest/'score.ly',engraving],log)
    run(['lilypond','-dno-point-and-click','-o',dest/'score',dest/'score.ly'],log)
    manifest = {'notes_unchanged':True,'performance_seconds':seconds(float(expanded.highestTime)),
                'audio_seconds':len(mix)/44100,'pre_scale_peak':peak,'scale':scale,
                'peak':float(np.max(np.abs(mix))),'staff_curves':len(audio),
                'soundfont':'FluidR3_GM.sf2','method':'continuous per-staff woven sound dynamics; repeated measures expanded',
                'warnings':[line for line in log.read_text().splitlines() if 'warning:' in line.lower() or 'error:' in line.lower()],
                'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}}
    (dest/'render.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('work',type=Path)
    p.add_argument('--output-name', default='render')
    a=p.parse_args(); render(a.work, a.output_name)
