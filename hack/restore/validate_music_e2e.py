"""Verify published hashes, real stereo audio, notation, and the MusicXML backup."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from scheherazade.restore import recover_works
from music_e2e import save


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--notes-only',action='store_true',help='Independently compare woven and rendered notation')
    a=p.parse_args();root=a.out;series=json.loads((root/'series.json').read_text())
    if a.notes_only:
        from music21 import converter
        from scheherazade.music.render import note_events
        rows=[]
        for w in series['works']:
            base=root/'full'/w['id']
            scores=[converter.parse(p).toSoundingPitch().stripTies()
                    for p in (base/'work.musicxml',base/'render/score.musicxml')]
            if note_events(scores[0])!=note_events(scores[1]):raise ValueError(f'render differs from carrier: {w["id"]}')
            rows.append({'id':w['id'],'rendered_notes_match_carrier':True})
            print(w['id'],'notes match',flush=True)
        save(root/'render-score-comparison.json',{'works':rows})
        return
    rows=[]
    for w in series['works']:
        base=root/'full'/w['id'];render=base/'render';notation=base/'notation-v2'
        manifest=json.loads((render/'render.json').read_text())
        for name,digest in manifest['artifacts'].items():
            if hashlib.sha256((render/name).read_bytes()).hexdigest()!=digest:raise ValueError(f'changed render {base}/{name}')
        layout=json.loads((notation/'verified.json').read_text())
        for name,digest in layout['sha256'].items():
            if hashlib.sha256((notation/name).read_bytes()).hexdigest()!=digest:raise ValueError('changed notation')
        if layout['warnings']:raise ValueError(f'notation warnings: {w["id"]}')
        for path in (base/'work.musicxml',notation/'score.pdf',render/'score.mp3'):
            if not path.stat().st_size:raise ValueError('empty artifact')
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(render/'score.mp3'),
                                     '-ac','2','-ar','44100','-f','f32le','-'])
        sound=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
        peak=float(np.max(np.abs(sound)));rms=float(np.sqrt(np.mean(sound**2)))
        seconds=len(sound)/44100
        if not .001<rms or not peak<1 or abs(seconds-w['seconds']-4)>.15:raise ValueError('audio peak/duration/silence')
        analysis=json.loads((render/'analysis.json').read_text())
        if manifest.get('renderer')=='native-sfz-1' and any(s.get('expression_knots',0)==0 for s in analysis['stems']):
            raise ValueError('missing woven expression in a sampled stem')
        rows.append({'id':w['id'],'seconds':seconds,'stereo_peak':peak,'stereo_rms':rms,
                     'published_render_hashes_verified':len(manifest['artifacts']),
                     'notation_notes_unchanged':layout['notes_unchanged'],'notation_warnings':layout['warnings']})
        print(json.dumps(rows[-1]),flush=True)
    key=X25519PrivateKey.from_private_bytes((root/'recipient.key').read_bytes())
    recovered,objects,report=recover_works(root/'surviving-musicxml',key)
    if hashlib.sha256(recovered).hexdigest()!=series['archive_sha256']:raise ValueError('final restore checksum')
    if report['rejected']:raise ValueError('rejected survivor')
    save(root/'validation.json',{'works':rows,'music_seconds':sum(w['seconds'] for w in series['works']),
         'audio_seconds':sum(w['seconds'] for w in rows),'objects':len(objects),'archive_identical':True,
         'decoded_musicxml':len(report['decoded']),'rejected_musicxml':report['rejected']})


if __name__=='__main__':main()
