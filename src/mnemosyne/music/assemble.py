"""From chosen candidates to a work: transposition to the key plan, the
title page, the score, the parts, the sound.

A nocturne is one piece; a symphony is four movements bound into one
score with a title page and movement titles. Each movement is transposed
to its place in the key plan (tonic, subdominant or relative, tonic,
tonic), the score and the parts are engraved with LilyPond, and the sound
uses the shared instrumentarium and native stereo SFZ renderer.
The former FluidSynth path is available only for explicit legacy replay.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from music21 import converter, interval, key, metadata, pitch, stream

from . import analyze

SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"


def _transpose_to(score, target_tonic: str, target_mode: str):
    k = score.analyze("key")
    if k.mode != target_mode:
        # Choose the tonic of the same mode closest to the target.
        target = key.Key(target_tonic, k.mode)
    else:
        target = key.Key(target_tonic, target_mode)
    iv = interval.Interval(k.tonic, target.tonic)
    if abs(iv.semitones) > 6:
        iv = interval.Interval(iv.semitones - 12 if iv.semitones > 0 else iv.semitones + 12)
    return score.transpose(iv), {"from": f"{k.tonic.name} {k.mode}", "to": f"{target.tonic.name} {target.mode}",
                                 "semitones": iv.semitones}


def render(xml: Path, out_dir: Path, stem: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    s = converter.parse(str(xml))
    midi = out_dir / f"{stem}.mid"
    s.write("midi", fp=str(midi))
    wav = out_dir / f"{stem}.wav"
    subprocess.run(["fluidsynth", "-ni", "-F", str(wav), "-r", "44100", SOUNDFONT, str(midi)],
                   check=True, capture_output=True, timeout=3600)
    flac = out_dir / f"{stem}.flac"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), str(flac)], check=False, timeout=600)
    return {"midi": str(midi), "audio": str(flac if flac.exists() else wav)}


def engrave(xml: Path, out_dir: Path, stem: str) -> dict:
    """Score PDF through LilyPond (musicxml2ly ships with it)."""
    ly = out_dir / f"{stem}.ly"
    subprocess.run(["musicxml2ly", "-o", str(ly), str(xml)], check=False, capture_output=True, timeout=600)
    r = subprocess.run(["lilypond", "-o", str(out_dir / stem), str(ly)], capture_output=True, timeout=1800)
    pdf = out_dir / f"{stem}.pdf"
    return {"pdf": str(pdf) if pdf.exists() else None, "lilypond_ok": r.returncode == 0}


def nocturne(choice: dict, cands: Path, out: Path, title: str, tonic: str, mode: str) -> dict:
    xml = analyze.to_musicxml(cands / choice["chosen"])
    s = converter.parse(str(xml))
    s, tr = _transpose_to(s, tonic, mode)
    s.metadata = metadata.Metadata(title=title, composer="Atelier")
    out.mkdir(parents=True, exist_ok=True)
    stem = out.name
    x = out / f"{stem}.musicxml"
    s.write("musicxml", fp=str(x))
    return {"score": str(x), "transposition": tr, **render(x, out, stem), **engrave(x, out, stem)}


KEY_PLAN = {
    "major": [("tonic", 0), ("subdominant", 5), ("tonic", 0), ("tonic", 0)],
    "minor": [("tonic", 0), ("relative major", 3), ("tonic", 0), ("tonic major", 0)],
}


def symphony(choice: dict, cands: dict[int, Path], out: Path, title: str, tonic: str, mode: str, *,
             native_bank: Path | None = Path("/work/samples/instrumentarium"),
             orchestration_plan: dict | None = None) -> dict:
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Preserved existing symphony: {out}; choose a new destination")
    out.mkdir(parents=True, exist_ok=True)
    movements, info = [], []
    base = pitch.Pitch(tonic)
    for (role, shift), mv in zip(KEY_PLAN[mode], sorted(choice["chosen"])):
        xml = analyze.to_musicxml(cands[mv] / choice["chosen"][mv])
        s = converter.parse(str(xml)).toSoundingPitch()
        target = base.transpose(shift)
        m = "major" if role in ("subdominant", "relative major", "tonic major") or mode == "major" else "minor"
        s, tr = _transpose_to(s, target.name, m)
        name = ["Allegro", "Adagio", "Scherzo", "Finale"][mv - 1]
        s.metadata = metadata.Metadata(title=f"{title} — {mv}. {name}", composer="Atelier")
        x = out / f"mv{mv}.musicxml"
        s.write("musicxml", fp=str(x))
        if native_bank is None:
            rendered={**render(x, out, f"mv{mv}"), **engrave(x, out, f"mv{mv}")}
        else:
            from .orchestration import orchestrate_existing
            from .orchestra_render import render_orchestra
            arranged,plan,assignment=orchestrate_existing(s,orchestration_plan)
            plan['transposition']=tr
            destination=out/f'mv{mv}-orchestrated'
            render_orchestra(arranged,plan,assignment,destination,native_bank)
            rendered={'score':str(destination/'score.musicxml'),'audio':str(destination/'score.mp3'),
                      'pdf':str(destination/'score.pdf'),'parts':str(destination/'parts'),
                      'manifest':str(destination/'render.json'),'original_score':str(x)}
        movements.append({"n": mv, "name": name, "role": role, "score": str(x), "transposition": tr,
                          **rendered})
    return {"title": title, "key": f"{tonic} {mode}", "movements": movements}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["nocturne", "symphony"])
    ap.add_argument("--choice", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--key", default="D- major", help="tonic and mode, e.g. 'D- major' or 'C# minor'")
    ap.add_argument('--sample-bank',type=Path,default=Path('/work/samples/instrumentarium'))
    ap.add_argument('--orchestration-plan',type=Path,help='Explicit ensemble/colour/line assignments for symphony')
    ap.add_argument('--legacy-soundfont',action='store_true',help='Replay the former GM symphony renderer')
    a = ap.parse_args()
    choice = json.loads(a.choice.read_text())
    tonic, mode = a.key.split()
    if a.kind == "nocturne":
        r = nocturne(choice, a.candidates, a.out, a.title, tonic, mode)
    else:
        r = symphony(choice, {i: a.candidates / f"mv{i}" for i in range(1, 5)}, a.out, a.title, tonic, mode,
                     native_bank=None if a.legacy_soundfont else a.sample_bank,
                     orchestration_plan=json.loads(a.orchestration_plan.read_text()) if a.orchestration_plan else None)
    (a.out / "work.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
    print(json.dumps(r, ensure_ascii=False)[:600])


if __name__ == "__main__":
    main()
