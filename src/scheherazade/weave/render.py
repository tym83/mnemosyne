"""Render the verified MusicXML in a studio using the existing music toolchain."""
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from music21 import converter, instrument
from scheherazade.music.render import note_events, run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('xml', type=Path)
    p.add_argument('--soundfont', type=Path, required=True)
    a = p.parse_args()
    stem = a.xml.with_suffix('')
    def dest(ext):
        return Path(str(stem) + ext)
    log = dest('.render.log')
    score = converter.parse(str(a.xml))
    for part in score.parts:
        for ins in list(part.recurse().getElementsByClass(instrument.Instrument)):
            ins.activeSite.remove(ins)
        part.insert(0, instrument.Piano())
    score.write('midi', fp=str(dest('.mid')))
    engraving = dest('.engraving.musicxml')
    score.write('musicxml', fp=str(engraving))
    tree = ET.parse(engraving)
    for ident in tree.findall('identification'):
        for creator in list(ident.findall('creator')):
            if creator.text == 'Music21':
                ident.remove(creator)
    tree.write(engraving, encoding='utf-8', xml_declaration=True)
    if note_events(score) != note_events(converter.parse(str(engraving))):
        raise RuntimeError('engraving round trip changed notes')
    run(['musicxml2ly', '-o', dest('.ly'), engraving], log)
    run(['lilypond', '-dno-point-and-click', '-o', stem, dest('.ly')], log)
    run(['fluidsynth', '-ni', '-o', 'synth.cpu-cores=1', '-g', '0.5',
         '-F', dest('.wav'), '-r', '44100', a.soundfont, dest('.mid')], log)
    run(['ffmpeg', '-nostdin', '-v', 'warning', '-threads', '1', '-i', dest('.wav'),
         '-af', 'alimiter=limit=0.95:level=false', '-codec:a', 'libmp3lame', '-q:a', '2',
         '-threads', '1', dest('.mp3')], log)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries',
                    'format=duration', '-of', 'json', str(dest('.mp3'))]))
    for ext in ('.pdf', '.mp3'):
        if not dest(ext).stat().st_size:
            raise RuntimeError('empty artifact')
    manifest = {'engraving_note_round_trip': True, 'audio_seconds': float(probe['format']['duration']),
                'warnings': [line for line in log.read_text().splitlines()
                             if any(w in line.lower() for w in ('warning:', 'error:', 'converted to slur'))]}
    dest('.render.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
