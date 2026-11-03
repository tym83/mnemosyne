"""Deterministic plate printing from a render and encoded world normals.

Runs with numpy/Pillow in the studio venv, never inside Blender. Tone controls
stroke width and the number of hatch families, not a grey render underneath.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

STYLES = {
    "etching": (6.5, 1.0, 0.0),
    "aquatint": (9.0, 0.7, 0.28),
    "ink_line": (10.0, 0.55, 0.0),
}


def plate(source: Path, normals: Path, output: Path, title: str, artist: str,
          number: str, style="etching", seed=1729):
    """Print at source resolution, reserving paper margins and a caption panel."""
    if style not in STYLES:
        raise ValueError(f"Unknown engraving style: {style}")
    src = Image.open(source).convert("RGBA")
    width, height = src.size
    margin = round(width * 0.045)
    top, bottom = round(height * 0.05), round(height * 0.83)
    iw, ih = width - 2 * margin, bottom - top
    # Fit the whole camera frame without cropping or distorting its geometry.
    ratio = min(iw / width, ih / height)
    rw, rh = round(width * ratio), round(height * ratio)
    left = (width - rw) // 2
    rgba = np.asarray(src.resize((rw, rh), Image.Resampling.LANCZOS), dtype=np.float32) / 255
    rgb, mask = rgba[..., :3], rgba[..., 3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    visible = lum[mask > 0.95]
    light = float(np.quantile(visible, .94)) if visible.size else .9
    dark_point = float(np.quantile(visible, .04)) if visible.size else .1
    # Open paper in the lights, with a full tonal range even for muted renders.
    tone = (np.clip((light - lum) / max(light - dark_point, .2), 0, 1) ** 1.25) * mask
    n = np.asarray(Image.open(normals).convert("RGB").resize((rw, rh)), dtype=np.float32) / 255
    # File Output stores linear RGB as sRGB; invert the transfer before decoding.
    n = np.where(n <= 0.04045, n / 12.92, ((n + 0.055) / 1.055) ** 2.4) * 2 - 1
    spacing, density, wash = STYLES[style]
    unit = width / 2700
    spacing *= unit
    y, x = np.mgrid[:rh, :rw].astype(np.float32)
    # Dominant world-normal families stay coherent on planes. Curved vaults
    # interpolate between families without multiplying coordinates by an angle.
    weights = np.abs(n) ** 5
    weights /= np.maximum(weights.sum(axis=2, keepdims=True), 1e-5)
    angles = (np.deg2rad(32), np.deg2rad(-32), np.deg2rad(8))
    ink = np.zeros_like(tone)
    for axis, angle in enumerate(angles):
        field = x * np.cos(angle) + y * np.sin(angle)
        field += 0.32 * unit * np.sin(y / (29 * unit)) + 0.25 * unit * np.sin(x / (53 * unit))
        for family, threshold in ((0, 0.04), (1, 0.48), (2, 0.82)):
            phase = (field if family == 0 else
                     (-x * np.sin(angle) + y * np.cos(angle)) if family == 1 else
                     (x * np.cos(angle + .65) + y * np.sin(angle + .65)))
            distance = np.abs((phase + spacing / 2) % spacing - spacing / 2)
            strength = np.clip((tone - threshold) / (1 - threshold), 0, 1)
            stroke = (0.10 + strength * 2.2 * density) * unit
            lines = np.clip(stroke + 0.5 - distance, 0, 1) * (strength > 0.015)
            # Taper/break strokes in pale passages instead of a uniform screen.
            taper = np.clip(strength * 5 - .35 + .35 * np.sin((x + y * .3) / (17 * unit)), 0, 1)
            ink += weights[..., axis] * lines * taper * .95
    # Edges of normals recover structural pen work; rendered Freestyle supplies
    # silhouettes and creases, including coplanar occlusions.
    edge = np.zeros_like(tone)
    for axis in (0, 1):
        edge = np.maximum(edge, np.linalg.norm(n - np.roll(n, 1, axis=axis), axis=2))
    contour = np.clip((edge - 0.18) * 1.8, 0, 0.85) * mask
    dark = np.asarray(Image.fromarray((lum * 255).astype('uint8')).filter(ImageFilter.MinFilter(3))) / 255
    pen = np.clip((0.18 - dark) * 4, 0, 0.65) * mask
    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 0.65, (height, width)).astype(np.float32)
    paper = np.array([244, 236, 218], dtype=np.float32)[None, None, :] + grain[..., None]
    coverage = np.clip(ink + contour + pen + wash * tone * rng.uniform(0.2, 1.2, tone.shape), 0, 0.96)
    coverage *= mask
    region = paper[top:top + rh, left:left + rw]
    region[:] = region * (1 - coverage[..., None]) + np.array([39, 34, 29]) * coverage[..., None]
    result = Image.fromarray(np.clip(paper, 0, 255).astype('uint8'))
    draw = ImageDraw.Draw(result)
    # The plate mark is a shallow pressed bevel around image and cartouche.
    box = (margin - 14 * unit, top - 15 * unit, width - margin + 14 * unit, height * 0.95)
    draw.rectangle(box, outline=(184, 174, 154), width=max(1, round(unit)))
    draw.rectangle(tuple(v + 2 * unit for v in box), outline=(255, 249, 232), width=max(1, round(unit)))
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

    def caption(text, y, size):
        text = " ".join(text.split())
        font = ImageFont.truetype(font_path, max(10, round(size * unit)))
        while draw.textlength(text, font=font) > iw * 0.92 and font.size > 10:
            font = ImageFont.truetype(font_path, font.size - 1)
        draw.text((width / 2, y), text, font=font, fill=(51, 44, 36), anchor="mt")

    line_y = height * 0.855
    draw.line((width * 0.36, line_y, width * 0.64, line_y), fill=(133, 121, 101), width=max(1, round(unit)))
    caption(title, height * 0.868, 30)
    caption(f"{artist}    ·    Лист {number}", height * 0.905, 20)
    result.save(output)


def difference(previous: Path, current: Path) -> dict:
    """Compare composition at low resolution, ignoring grain and cartouches."""
    def sample(path):
        im = Image.open(path).convert("L")
        w, h = im.size
        return np.asarray(im.crop((w * .09, h * .05, w * .91, h * .83))
                          .resize((128, 80), Image.Resampling.LANCZOS), dtype=float) / 255
    delta = np.abs(sample(previous) - sample(current))
    mae, changed = float(delta.mean()), float((delta > .08).mean())
    return {"mean_difference": mae, "changed_fraction": changed,
            "barely_changed": mae < .025 and changed < .08}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--title", default="Этюд")
    ap.add_argument("--artist", default="")
    ap.add_argument("--number", default="1")
    ap.add_argument("--style", choices=STYLES)
    a = ap.parse_args()
    style = a.style or a.source.with_suffix('.style').read_text().strip()
    plate(a.source, a.source.with_name(a.source.stem + '_normals.png'), a.output,
          a.title, a.artist, a.number, style)


if __name__ == '__main__':
    main()
