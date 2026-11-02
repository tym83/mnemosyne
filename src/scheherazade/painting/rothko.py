"""Colour-field painting after Rothko: a window as two or three soft fields.

The proportions of the fields are the proportions of the window's life:
the share of time in trouble or crowds sets the height of the dark field,
the peak of tension the intensity of the band between fields, the season
and the temperament of the cluster the palette. Paint is laid in glazes —
many thin translucent layers with ragged edges — so the fields breathe
the way Rothko's do, rather than being flat rectangles.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# Palettes as (ground, upper field, band, lower field), in the spirit of
# the periods of the painter: the warm classic fields, the Seagram murals,
# the late greys.
PALETTES = {
    "warm": [(118, 32, 24), (196, 64, 28), (232, 148, 48), (92, 18, 22)],
    "seagram": [(52, 14, 16), (110, 24, 24), (150, 52, 30), (40, 10, 14)],
    "late-grey": [(28, 28, 32), (40, 40, 46), (96, 96, 104), (120, 118, 122)],
    "blue-dusk": [(24, 34, 58), (38, 62, 104), (122, 150, 176), (30, 40, 62)],
    "ochre": [(160, 120, 60), (208, 168, 84), (236, 210, 140), (130, 88, 44)],
}


def _noise(h, w, rng, scale):
    small = rng.random((max(2, h // scale), max(2, w // scale)))
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(img, dtype=float) / 255


def _field(h, w, top, bottom, left, right, rng, softness):
    """A ragged rectangle mask with soft, breathing edges."""
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    wob_y = (_noise(h, w, rng, 60) - 0.5) * softness * 2
    wob_x = (_noise(h, w, rng, 60) - 0.5) * softness * 2
    m = (y > top + wob_y) & (y < bottom + wob_y) & (x > left + wob_x) & (x < right + wob_x)
    img = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(softness))
    return np.asarray(img, dtype=float) / 255


def paint(material: dict, seed: int, out: Path, size=(1800, 2250)) -> dict:
    rng = np.random.default_rng(seed)
    w, h = size
    acts = material["skeleton"]
    tension = np.array(material["tension"], dtype=float)
    dark_share = float((tension > 0.35).mean())
    crowd = any(f["function"] == "crowd" for a in acts for f in a["functions"])
    peak = float(tension.max()) if len(tension) else 0.0
    month = int(material["window"].split("-")[1][:2]) if material["window"].startswith(("month:", "day:")) else datetime.fromisoformat(material["to"]).month
    if peak > 0.6 and crowd:
        palette = "warm" if rng.random() < 0.6 else "seagram"
    elif peak > 0.6:
        palette = "seagram"
    elif month in (11, 12, 1, 2):
        palette = "late-grey" if rng.random() < 0.5 else "blue-dusk"
    else:
        palette = "ochre"
    ground, upper, band, lower = (np.array(c, dtype=float) for c in PALETTES[palette])
    canvas = np.ones((h, w, 3)) * ground
    margin_x = int(w * rng.uniform(0.07, 0.11))
    top_m = int(h * rng.uniform(0.05, 0.08))
    bot_m = int(h * rng.uniform(0.06, 0.1))
    # The dark field grows with the share of trouble; the band with the peak.
    split = top_m + (h - top_m - bot_m) * (0.62 - 0.35 * min(1, dark_share * 6))
    band_h = h * (0.015 + 0.06 * peak)
    fields = [
        (upper, top_m, split - band_h / 2),
        (band, split - band_h / 2, split + band_h / 2),
        (lower, split + band_h / 2, h - bot_m),
    ]
    layers = 14
    for k in range(layers):
        for colour, t, b in fields:
            jitter = rng.normal(0, 10, 3)
            mask = _field(h, w, t, b, margin_x, w - margin_x, rng, softness=rng.uniform(8, 26))
            # Brush: long horizontal strokes, thin and uneven, scumbled over.
            sy, sx = max(2, h // int(rng.integers(4, 9))), max(2, w // int(rng.integers(90, 220)))
            strokes = np.asarray(Image.fromarray((rng.random((sy, sx)) * 255).astype(np.uint8))
                                 .resize((w, h), Image.BICUBIC), dtype=float) / 255
            alpha = (mask * (0.55 + 0.9 * strokes))[..., None] * rng.uniform(0.07, 0.15)
            canvas = canvas * (1 - alpha) + (colour + jitter) * alpha
    grain = (_noise(h, w, rng, 3) - 0.5) * 10 + (_noise(h, w, rng, 1) - 0.5) * 6
    canvas = np.clip(canvas + grain[..., None], 0, 255).astype(np.uint8)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(canvas).save(out)
    return {"school": "colour-field (Rothko)", "palette": palette, "dark_share": round(dark_share, 3),
            "peak": round(peak, 3), "split": round(split / h, 3), "band": round(band_h / h, 3), "layers": layers}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("materials", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("out/works/painting"))
    ap.add_argument("--trials", type=int, default=4)
    a = ap.parse_args()
    for p in a.materials:
        m = json.loads(p.read_text())
        stem = f"{m['cluster']}_{m['window'].replace(':', '_')}_rothko"
        base = int.from_bytes(hashlib.sha256(stem.encode()).digest()[:4], "big")
        trials = []
        for t in range(a.trials):
            f = a.out / "sketches" / f"{stem}_{t}.png"
            info = paint(m, base + t, f, size=(480, 600))
            trials.append({"file": str(f), **info})
        # The final canvas repeats the trial the workshop keeps (first, for now:
        # the choice among trials belongs to the critics and the patron).
        final = paint(m, base, a.out / f"{stem}.png")
        (a.out / f"{stem}.json").write_text(json.dumps({"material": str(p), "final": final, "sketches": trials}, indent=1))
        print(stem, final)


if __name__ == "__main__":
    main()
