"""Underpainting after Hokusai's Great Wave, and its painting by a model.

The composition is decided here, by code, before any model sees it: the
crest line of the wave is the tension curve of the window, the boats are
the characters who took part, a small Fuji in the distance is the part of
the cluster nobody can reach. The underpainting is a flat woodblock-like
image in the print's palette; a diffusion model (FLUX.1-schnell,
image-to-image, on the studio's CPUs) then paints over it at a strength
that keeps the composition.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PRUSSIAN = (28, 52, 92)
INDIGO = (46, 78, 120)
FOAM = (236, 230, 214)
SKY = (226, 214, 186)
BOAT = (196, 170, 120)


def underpainting(material: dict, seed: int, size=(1344, 896)) -> tuple[Image.Image, dict]:
    rng = np.random.default_rng(seed)
    w, h = size
    img = Image.new("RGB", size, SKY)
    d = ImageDraw.Draw(img)
    # Sky gradient, darker at the top as in the print.
    for y in range(h // 2):
        t = y / (h / 2)
        c = tuple(int(a * (0.75 + 0.25 * t) + b * (0.25 - 0.25 * t)) for a, b in zip(SKY, (120, 110, 100)))
        d.line([(0, y), (w, y)], fill=c)
    tension = np.array(material["tension"], dtype=float)
    xs = np.linspace(0, w, 400)
    sea = h * 0.72
    t = np.interp(np.linspace(0, len(tension) - 1, len(xs)), np.arange(len(tension)), tension)
    # The great wave is the window's worst moment: its height is the peak of
    # tension (absolute, so a calm week has a calm sea), its breadth how long
    # the trouble lasted, its place when it came. Smaller swells follow the
    # rest of the curve.
    A = float(min(1.0, tension.max()))
    x0 = float(np.argmax(t) / len(t) * w)
    hot = float((tension > 0.35).mean())
    sigma = w * (0.07 + 0.5 * hot ** 0.5)
    body = A * np.exp(-0.5 * ((xs - x0) / sigma) ** 2) * np.where(xs < x0, 1.0, 0.55 + 0.45 * np.exp(-((xs - x0) / sigma)))
    swell = np.convolve(t, np.ones(25) / 25, mode="same")
    swell_only = sea - h * (0.12 * swell + 0.02 * np.sin(xs / 37 + rng.uniform(0, 6)) + 0.05 * A * body)
    d.polygon([(0, h)] + [(float(x), float(y)) for x, y in zip(xs, swell_only)] + [(w, h)], fill=PRUSSIAN)
    d.line([(float(x), float(y + 14)) for x, y in zip(xs, swell_only)], fill=INDIGO, width=10)
    peak_i = int(np.argmax(t))
    if A > 0.3:
        # Hokusai's wave: a long back slope, a crest that overhangs towards
        # the boats and breaks into claws of foam.
        H = h * 0.62 * A
        bw = sigma * 1.4
        cx, top = min(w * 0.85, max(w * 0.35, x0)), sea - H
        def bez(p0, p1, p2, p3, n=40):
            tt = np.linspace(0, 1, n)[:, None]
            return ((1 - tt) ** 3 * p0 + 3 * (1 - tt) ** 2 * tt * p1 + 3 * (1 - tt) * tt ** 2 * p2 + tt ** 3 * p3)
        P = lambda x, y: np.array([x, y], dtype=float)
        back = bez(P(cx + 2.4 * bw, sea), P(cx + 1.4 * bw, sea - 0.2 * H), P(cx + 0.5 * bw, top - 0.05 * H), P(cx, top))
        hook = bez(P(cx, top), P(cx - 0.6 * bw, top - 0.02 * H), P(cx - 1.05 * bw, top + 0.25 * H), P(cx - 0.8 * bw, top + 0.45 * H))
        curl = bez(P(cx - 0.8 * bw, top + 0.45 * H), P(cx - 0.55 * bw, top + 0.55 * H), P(cx - 0.35 * bw, top + 0.3 * H), P(cx - 0.42 * bw, top + 0.2 * H))
        face = bez(P(cx - 0.42 * bw, top + 0.2 * H), P(cx - 0.1 * bw, top + 0.45 * H), P(cx - 0.35 * bw, sea - 0.15 * H), P(cx - 0.9 * bw, sea))
        outline = np.vstack([back, hook, curl, face])
        d.polygon([tuple(p) for p in outline], fill=PRUSSIAN)
        d.line([tuple(p) for p in np.vstack([back[10:], hook])], fill=INDIGO, width=22)
        # Claws: foam fingers along the overhang.
        for q in np.vstack([hook, curl[:20]]):
            for _ in range(3):
                r = rng.uniform(5, 13)
                fx_, fy_ = q[0] + rng.normal(0, 9), q[1] + rng.normal(0, 7)
                d.ellipse([fx_ - r, fy_ - r, fx_ + r, fy_ + r], fill=FOAM)
        for q in back[::3]:
            r = rng.uniform(3, 7)
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=FOAM)
        peak_i = int(cx / w * len(xs))
    # A small Fuji far away: the unreachable part of the cluster.
    fx = w * (0.62 if peak_i < len(xs) * 0.5 else 0.3)
    d.polygon([(fx - 80, sea), (fx, sea - 70), (fx + 80, sea)], fill=INDIGO)
    d.polygon([(fx - 22, sea - 52), (fx, sea - 70), (fx + 22, sea - 52)], fill=FOAM)
    # Boats: one for each character, rowing under the wave.
    chars = material.get("characters", [])
    for j, c in enumerate(chars[:5]):
        bx = w * (0.2 + 0.6 * (j + 0.5) / max(1, min(5, len(chars))))
        by = sea - 10 + rng.normal(0, 12)
        tilt = rng.normal(0, 0.15)
        L = 150
        pts = [(bx - L / 2, by), (bx + L / 2, by + L * tilt), (bx + L / 2 - 20, by + 18 + L * tilt), (bx - L / 2 + 20, by + 18)]
        d.polygon(pts, fill=BOAT)
        for r in range(6):
            rx = bx - L / 2 + 30 + r * 18
            d.ellipse([rx - 5, by - 14, rx + 5, by - 4], fill=(40, 40, 50))
    # Lower sea: the troughs.
    for k in range(6):
        y = sea + 20 + k * 28
        d.arc([-200 + k * 40, y - 30, w * 0.7, y + 60], 200, 340, fill=FOAM, width=4)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    return img, {"peak_at": round(peak_i / len(xs), 3), "peak": round(A, 3), "breadth": round(sigma / w, 3),
                 "boats": min(5, len(chars))}


PROMPT = ("ukiyo-e woodblock print in the style of Katsushika Hokusai, a great wave about to break over "
          "small rowing boats, claws of white foam, Mount Fuji small in the distance, Prussian blue and "
          "indigo, cream sky, visible wood grain and paper texture, Edo period, masterpiece")


def paint_flux(under: Image.Image, out: Path, seed: int, strength: float = 0.62, steps: int = 4):
    """Runs in the studio: FLUX.1-schnell image-to-image on CPU."""
    import torch
    from diffusers import AutoPipelineForImage2Image

    import os
    model = os.environ.get("MNEMOSYNE_PAINT_MODEL")
    if not model:
        raise RuntimeError("configure MNEMOSYNE_PAINT_MODEL with local weights or a model repository")
    pipe = AutoPipelineForImage2Image.from_pretrained(model, torch_dtype=torch.bfloat16)
    g = torch.Generator().manual_seed(seed)
    img = pipe(PROMPT, image=under, strength=strength, num_inference_steps=steps, guidance_scale=0.0,
               height=under.height, width=under.width, generator=g).images[0]
    img.save(out)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("materials", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/works/painting"))
    ap.add_argument("--flux", action="store_true", help="paint over with the model (studio only)")
    ap.add_argument("--variants", type=int, default=3)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for p in a.materials:
        m = json.loads(p.read_text())
        stem = f"{m['cluster']}_{m['window'].replace(':', '_')}_wave"
        base = int.from_bytes(hashlib.sha256(stem.encode()).digest()[:4], "big")
        under, info = underpainting(m, base)
        under.save(a.out / f"{stem}_under.png")
        rec = {"material": str(p), "school": "ukiyo-e (Hokusai)", "composition": info, "prompt": PROMPT, "variants": []}
        if a.flux:
            for v in range(a.variants):
                f = a.out / f"{stem}_v{v}.png"
                paint_flux(under, f, base + v)
                rec["variants"].append(str(f))
        (a.out / f"{stem}.json").write_text(json.dumps(rec, indent=1))
        print(stem, info)


if __name__ == "__main__":
    main()
