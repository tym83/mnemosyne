"""What a generated piece actually is: features read from the score.

A piece from the model is a candidate, not a work. Before anything is
chosen, its score is read like a teacher reads a student's exercise: key,
metre, tempo, length, the parts and their ranges, how dense each bar is,
and whether the opening ever comes back. These numbers are what the
critics compare against the plan of the work.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ABC2XML = Path(os.environ.get("ABC2XML", "/work/NotaGen/gradio/abc2xml.py"))


def to_musicxml(abc: Path) -> Path:
    out = abc.with_suffix(".xml")
    if not out.exists():
        subprocess.run([sys.executable, str(ABC2XML), "-o", str(abc.parent), str(abc)],
                       check=True, capture_output=True, timeout=120)
    return out


def _interval_profile(notes) -> np.ndarray:
    v = np.zeros(25)
    for a, b in zip(notes, notes[1:]):
        d = int(np.clip(b - a, -12, 12)) + 12
        v[d] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


def features(xml: Path) -> dict:
    from music21 import converter, dynamics, meter, note, tempo

    s = converter.parse(str(xml))
    parts = list(s.parts)
    top = parts[0] if parts else s
    measures = top.getElementsByClass("Measure")
    bars = len(measures)
    ts = s.recurse().getElementsByClass(meter.TimeSignature)
    ts0 = ts[0].ratioString if ts else "4/4"
    mm = s.recurse().getElementsByClass(tempo.MetronomeMark)
    bpm = float(mm[0].number) if mm and mm[0].number else None
    k = s.analyze("key")
    # Density per bar across all parts: notes started in that bar.
    dens = np.zeros(max(bars, 1))
    span = np.zeros(max(bars, 1))
    for p in parts:
        for i, m in enumerate(p.getElementsByClass("Measure")):
            if i >= len(dens):
                break
            ps = [n.pitch.midi for n in m.recurse().notes if isinstance(n, note.Note)]
            ps += [x.midi for c in m.recurse().getElementsByClass("Chord") for x in c.pitches]
            dens[i] += len(ps)
            if ps:
                span[i] = max(span[i], max(ps) - min(ps))
    dyn = [d.volumeScalar for d in s.recurse().getElementsByClass(dynamics.Dynamic) if d.volumeScalar is not None]
    # Melody of the top part: opening motif and whether it returns later.
    mel = [n.pitch.midi for n in top.recurse().notes if isinstance(n, note.Note)]
    durs = [float(n.quarterLength) for n in top.recurse().notes if isinstance(n, note.Note)]
    motif = mel[:10]
    head = _interval_profile(mel[: min(24, len(mel))])
    reprise = 0.0
    if len(mel) > 60:
        third = len(mel) * 2 // 3
        for j in range(third, len(mel) - 24, 4):
            reprise = max(reprise, float(head @ _interval_profile(mel[j:j + 24])))
    ranges = []
    for p in parts:
        ins = p.getInstrument(returnDefault=True)
        ps = [n.pitch.midi for n in p.recurse().notes if isinstance(n, note.Note)]
        lo = ins.lowestNote.midi if ins.lowestNote else None
        hi = ins.highestNote.midi if ins.highestNote else None
        out_of = sum(1 for x in ps if (lo and x < lo) or (hi and x > hi))
        ranges.append({"part": p.partName or ins.instrumentName, "notes": len(ps), "out_of_range": out_of})
    beats = float(ts[0].beatCount) if ts else 4.0
    seconds = bars * beats * 60 / bpm if bpm else None
    return {
        "bars": bars, "time_signature": ts0, "bpm": bpm, "seconds": seconds,
        "key": f"{k.tonic.name} {k.mode}", "mode": k.mode, "key_confidence": round(float(k.correlationCoefficient), 3),
        "parts": len(parts), "ranges": ranges,
        "density": dens.round(1).tolist(), "span": span.tolist(),
        "dynamics_mean": round(float(np.mean(dyn)), 3) if dyn else None,
        "motif": motif, "motif_durations": durs[:10],
        "reprise": round(reprise, 3),
        "mean_duration": round(float(np.mean(durs)), 3) if durs else None,
    }


def tension_proxy(f: dict, points: int = 96) -> np.ndarray:
    """A piece's own tension: denser and wider bars are tenser."""
    d = np.array(f["density"], dtype=float)
    sp = np.array(f["span"], dtype=float)
    if len(d) < 2:
        return np.zeros(points)
    z = lambda x: (x - x.mean()) / (x.std() + 1e-6)
    t = z(d) + 0.6 * z(sp)
    t = np.convolve(t, np.ones(3) / 3, mode="same")
    xs = np.linspace(0, len(t) - 1, points)
    return np.interp(xs, np.arange(len(t)), t)


def motif_similarity(a: list[int], b: list[int]) -> float:
    if len(a) < 4 or len(b) < 4:
        return 0.0
    return float(_interval_profile(a) @ _interval_profile(b))
