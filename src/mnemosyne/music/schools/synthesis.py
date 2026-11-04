"""Original procedural technique approximations; no recordings or third-party samples.

Algorithm and generated waveforms dedicated to CC0-1.0. These are not claims
of sampled acoustic preparations or authentic extended string techniques.
"""
import wave
import numpy as np
from .performance import sounding_events

LICENSE = 'Original procedural waveforms: CC0-1.0, https://creativecommons.org/publicdomain/zero/1.0/\nNo third-party recordings. Technique simulations, not acoustic samples.\n'


def render_synthesis(score, plan, path):
    rate = 22050
    audio = np.zeros((round((plan['duration']+2)*rate), 2), dtype=np.float32)
    rng = np.random.default_rng(plan['seed'])
    school = plan['school']
    seconds = 60/plan['tempo']
    for i, part in enumerate(score.parts):
        pan = (i+.5)/len(score.parts)
        for at, length, pitches, velocity, glide in sounding_events(part):
            start = round(at*seconds*rate)
            n = min(round(length*seconds*rate), len(audio)-start)
            t = np.arange(n)/rate
            if not n:
                continue
            signal = np.zeros(n)
            for pitch in pitches:
                frequency = 440*2**((pitch-69)/12)
                if glide:
                    duration, delta = glide
                    frequencies = frequency*2**(delta*np.minimum(t/(duration*seconds), 1)/12)
                    phase = 2*np.pi*np.cumsum(frequencies)/rate
                else:
                    phase = 2*np.pi*frequency*t
                progress = at / float(score.highestTime)
                if school == 'chance':
                    # Fixed preparation per key: detuned metal resonances + damped attack.
                    ratios = (1, 1.414+int(pitch)%5*.013, 2.73, 4.17)
                    voice = sum(np.sin(phase*r)*np.exp(-t*(1+k*.8))/(k+1) for k,r in enumerate(ratios))
                    voice += rng.normal(0, .12, n)*np.exp(-t*30)
                elif school == 'sonorism':
                    zone = min(2, int(progress*3))
                    voice = sum(np.sin(phase*k)/(k**(.6 if zone == 0 else 1.2)) for k in range(1, 13))*.15
                    noise = rng.normal(0, .2, n)
                    voice += noise * (np.exp(-t*15) if zone == 1 else .3)
                    if zone == 1:
                        voice *= np.exp(-t*4)
                elif school == 'scelsi':
                    brightness = .15+.75*np.sin(np.pi*progress)**2
                    voice = np.sin(phase)+sum(np.sin(phase*k)*brightness**(k-1)/k for k in range(2, 7))
                    voice *= .7+.3*np.sin(2*np.pi*.17*t+i)
                else:
                    voice = np.sin(phase)+.12*np.sin(phase*2)
                signal += voice/max(1,len(pitches))
            attack = .008 if school == 'chance' else min(.5, len(t)/rate/4)
            envelope = np.minimum(t/attack, 1)*np.minimum((n-1-np.arange(n))/rate/.08, 1)
            curve = getattr(part.editorial, 'school_expression', None)
            if curve:
                times, gains = zip(*curve)
                envelope *= np.interp(at+t/seconds, times, gains)
            signal = (signal*envelope*(velocity/127)**1.5*.15/max(1,len(score.parts))**.5).astype(np.float32)
            audio[start:start+n, 0] += signal*np.sqrt(1-pan)
            audio[start:start+n, 1] += signal*np.sqrt(pan)
    if np.max(np.abs(audio)) >= 1:
        raise ValueError('synthesis clipping')
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((audio*32767).astype('<i2').tobytes())
