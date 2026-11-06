"""Measured sample duration, embedded WAV loops and honest sample-derived sustain."""
from functools import lru_cache
import json
from pathlib import Path
import struct
import subprocess
import numpy as np


@lru_cache(maxsize=None)
def audio_info(path):
    value = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
        'stream=sample_rate,duration,channels','-of','json',str(path)]))['streams'][0]
    return {'rate': int(value['sample_rate']), 'seconds': float(value['duration']), 'channels': int(value['channels'])}


def embedded_loop(path):
    with Path(path).open('rb') as file:
        if file.read(4) != b'RIFF': return None
        file.read(8)
        while header := file.read(8):
            if len(header) != 8: break
            tag, size = struct.unpack('<4sI', header)
            if tag == b'smpl':
                body = file.read(size)
                if len(body) >= 60 and struct.unpack_from('<I', body, 28)[0]:
                    _, kind, start, end, _, _ = struct.unpack_from('<6I', body, 36)
                    if kind == 0 and end > start: return start, end
            else: file.seek(size, 1)
            if size % 2: file.seek(1, 1)
    return None


def crossfade_loop(pcm, rate):
    """Keep attack and tail; crossfade a middle segment of the SAME recording.

    The loop ends just before a blended pre-start segment, making the wrap
    continuous. No oscillator, pitch substitution or invented sample content.
    """
    if len(pcm) < rate * .4: raise ValueError('Sample too short for a sustain loop')
    start = int(min(1., len(pcm)/rate*.3)*rate)
    end = int(min(3., len(pcm)/rate*.75)*rate)
    fade = min(round(.1*rate), (end-start)//4, start)
    if fade < 2: raise ValueError('No usable sustain segment')
    result = pcm.copy()
    weight = np.linspace(0,1,fade)
    if pcm.ndim > 1: weight = weight[:,None]
    result[end-fade:end] = pcm[end-fade:end]*(1-weight) + pcm[start-fade:start]*weight
    return result, start, end-1


def prepare_region(zone, profile, destination):
    """Return explicit playback overrides and measurements for the manifest."""
    source = Path(zone['sample']); op = zone['opcodes']; info = audio_info(str(source))
    result = {'sample_seconds': info['seconds'], 'release_seconds': profile['release_seconds'],
              'source_sample': str(source), 'sustain': 'natural-decay'}
    overrides = {'ampeg_release': profile['release_seconds']}
    if not profile.get('sustained') or op.get('loop_mode') == 'one_shot' or zone.get('trigger', 'attack') not in ('attack','first','legato'): return overrides, result
    loop = None
    if op.get('loop_mode') not in ('no_loop', 'one_shot'):
        if 'loop_start' in op and 'loop_end' in op:
            loop = int(op['loop_start']), int(op['loop_end'])
        else: loop = embedded_loop(source)
    if loop:
        if not 0 <= loop[0] < loop[1] < round(info['seconds']*info['rate']):
            raise ValueError(f'Invalid library loop: {source}')
        overrides.update(loop_mode='loop_continuous', loop_start=loop[0], loop_end=loop[1])
        result.update(sustain='library-loop', loop_start=loop[0], loop_end=loop[1])
    else:
        import hashlib
        target = destination.parent/'sustain'/f'{hashlib.sha256(str(source).encode()).hexdigest()[:24]}.wav'
        target.parent.mkdir(exist_ok=True)
        raw = subprocess.check_output(['ffmpeg','-v','error','-i',source,'-f','f32le','-'])
        pcm = np.frombuffer(raw,dtype='<f4').reshape(-1,info['channels'])
        pcm, start, end = crossfade_loop(pcm, info['rate'])
        if not target.exists():
            subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar',str(info['rate']),'-ac',str(info['channels']),
                '-i','-','-c:a','pcm_s24le',str(target)],input=pcm.astype('<f4').tobytes(),check=True)
        overrides.update(sample=str(target.resolve()), loop_mode='loop_continuous', loop_start=start, loop_end=end)
        result.update(sustain='same-sample-crossfade', loop_start=start, loop_end=end,
                      crossfade_seconds=min(.1,(end+1-start)/info['rate']/4,start/info['rate']), playback_sample=str(target),
                      playback_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    return overrides, result
