"""Reproducible boundary/tail measurements; run full audio analyses in a studio."""
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
from music21 import converter
from .schools.performance import sounding_events

RATE=44100


def rms_db(data):
    return 20*np.log10(max(1e-12,float(np.sqrt(np.mean(np.asarray(data,dtype=float)**2))))) if len(data) else None


def measure(data, boundaries, final_note, score_end, rate=RATE):
    def window(a,b):return data[max(0,round(a*rate)):min(len(data),round(b*rate))]
    rows=[]
    for boundary in sorted(set(boundaries)):
        # 5 ms RMS bins; compare any two bins at most 30 ms apart near boundary.
        times=boundary+np.arange(-.03,.0301,.005)
        levels=[rms_db(window(t,t+.005)) for t in times]
        drops=[levels[i]-levels[j] for i in range(len(levels)) for j in range(i+1,min(i+7,len(levels)))
               if levels[i] is not None and levels[j] is not None and levels[i]>-80]
        rows.append({'seconds':boundary,'rms_before_50ms_dbfs':rms_db(window(boundary-.06,boundary-.04)),
                     'rms_after_150ms_dbfs':rms_db(window(boundary+.14,boundary+.16)),
                     'max_drop_within_30ms_db':max(drops,default=0)})
    tail=[{'after_final_note_seconds':float(t),'rms_dbfs':rms_db(window(final_note+t,final_note+t+.1))}
          for t in np.arange(0,max(0,len(data)/rate-final_note),.5)]
    return {'boundary_count':len(rows),'drops_over_20db':int(sum(r['max_drop_within_30ms_db']>20 for r in rows)),
            'boundaries':rows,'final_note_seconds':final_note,'score_end_seconds':score_end,
            'audio_seconds':len(data)/rate,'last_100ms_dbfs':rms_db(data[-round(.1*rate):]),'decay':tail}


def measure_work(root):
    from .tempo_map import seconds_at
    root=Path(root);plan=json.loads((root/'plan.json').read_text())
    score=converter.parse(root/'score.musicxml').toSoundingPitch()
    times=[];end=0.
    for part in score.parts:
        for at,length,*_ in sounding_events(part):
            times.extend([seconds_at(plan,at),seconds_at(plan,at+length)]);end=max(end,seconds_at(plan,at+length))
    audio=root/('score.flac' if (root/'score.flac').exists() else 'score.mp3')
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',audio,'-ar',str(RATE),'-ac','2','-f','f32le','-'])
    data=np.frombuffer(raw,dtype='<f4').reshape(-1,2)
    return measure(data,[t for t in times if t>0],end,plan['duration'])


def main():
    ap=argparse.ArgumentParser();ap.add_argument('before',type=Path);ap.add_argument('after',type=Path);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();result={'method':'stereo RMS, 20 ms windows centered at -50/+150 ms; drop search uses 5 ms RMS bins within +/-30 ms and separations <=30 ms; floor -80 dBFS',
                                'before':measure_work(args.before),'after':measure_work(args.after)}
    args.out.write_text(json.dumps(result,indent=2,default=lambda o:o.item()))
    print(json.dumps({k:{x:v[x] for x in ('boundary_count','drops_over_20db','audio_seconds','last_100ms_dbfs')} for k,v in result.items() if isinstance(v,dict)},indent=2))

if __name__=='__main__':main()
