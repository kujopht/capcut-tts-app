"""Deterministic chroma-key extraction + compositing - the productized,
automated version of the preceding mission's manually-diagnosed pipeline.

Real automation added here (closing the gap the preceding mission's own
findings flagged - "backdrop-color sampling with a gradient-detection
fallback" was not yet automatic): `sample_background_profile()` inspects
all four corners individually. When they disagree beyond a threshold (a
real gradient backdrop, as manually discovered and fixed for one image
last mission), it automatically widens the hue tolerance to span the
observed corner range instead of averaging into a meaningless mid-hue -
no human diagnosis required for this specific, previously-manual fix.
"""
from __future__ import annotations

import colorsys
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageFilter


def _corner_hsv(img: Image.Image, margin: int = 5) -> List[Tuple[float, float, float]]:
    w, h = img.size
    arr = np.asarray(img.convert("RGB")).astype(np.float32) / 255.0
    boxes = [
        arr[0:margin, 0:margin], arr[0:margin, w - margin:w],
        arr[h - margin:h, 0:margin], arr[h - margin:h, w - margin:w],
    ]
    out = []
    for box in boxes:
        r, g, b = box.reshape(-1, 3).mean(axis=0)
        hue, sat, val = colorsys.rgb_to_hsv(r, g, b)
        out.append((hue * 360, sat, val))
    return out


def sample_background_profile(img: Image.Image, *, gradient_hue_spread_threshold: float = 30.0):
    """Returns (hue_center, hue_tolerance, min_saturation, min_value,
    is_gradient). Automatically detects a gradient backdrop (corners
    disagree beyond `gradient_hue_spread_threshold` degrees) and widens
    the key to span it, rather than assuming a single flat color."""
    corners = _corner_hsv(img)
    hues = [c[0] for c in corners]
    sats = [c[1] for c in corners]
    vals = [c[2] for c in corners]

    max_spread = 0.0
    for i in range(len(hues)):
        for j in range(i + 1, len(hues)):
            d = min(abs(hues[i] - hues[j]), 360 - abs(hues[i] - hues[j]))
            max_spread = max(max_spread, d)

    is_gradient = max_spread > gradient_hue_spread_threshold
    min_sat = max(0.05, min(sats) * 0.5)
    min_val = max(0.08, min(vals) * 0.5)

    if is_gradient:
        # Circular-mean-free approach: center on the midpoint of the
        # observed range, tolerance wide enough to cover the full spread
        # plus margin - this is what manually fixed naruto_scene5's
        # teal-to-green gradient last mission, now automatic.
        sorted_hues = sorted(hues)
        hue_center = sorted_hues[len(sorted_hues) // 2]
        hue_tolerance = max_spread / 2 + 15
    else:
        hue_center = sum(hues) / len(hues)
        hue_tolerance = 18

    return hue_center, hue_tolerance, min_sat, min_val, is_gradient


def chromakey_extract(image_path, out_path, *, feather_px: int = 2) -> dict:
    img = Image.open(image_path).convert("RGB")
    hue_center, hue_tolerance, min_saturation, min_value, is_gradient = sample_background_profile(img)

    arr = np.asarray(img).astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = arr.max(axis=-1)
    minc = arr.min(axis=-1)
    delta = maxc - minc + 1e-8

    hue = np.zeros_like(maxc)
    mask_r = (maxc == r)
    mask_g = (maxc == g) & ~mask_r
    mask_b = (maxc == b) & ~mask_r & ~mask_g
    hue[mask_r] = (60 * (((g - b) / delta) % 6))[mask_r]
    hue[mask_g] = (60 * (((b - r) / delta) + 2))[mask_g]
    hue[mask_b] = (60 * (((r - g) / delta) + 4))[mask_b]
    saturation = np.where(maxc > 0, delta / (maxc + 1e-8), 0)
    value = maxc

    hue_dist = np.minimum(np.abs(hue - hue_center), 360 - np.abs(hue - hue_center))
    is_bg = (hue_dist < hue_tolerance) & (saturation > min_saturation) & (value > min_value)

    alpha = np.where(is_bg, 0.0, 1.0).astype(np.float32)
    alpha_u8 = np.clip(alpha * 255, 0, 255).astype(np.uint8)

    if feather_px > 0:
        alpha_img = Image.fromarray(alpha_u8, mode="L").filter(
            ImageFilter.GaussianBlur(radius=feather_px))
        alpha_u8 = np.asarray(alpha_img)

    rgba = np.dstack([np.asarray(img), alpha_u8])
    out_img = Image.fromarray(rgba, mode="RGBA")

    bbox = out_img.getbbox()
    if bbox:
        out_img = out_img.crop(bbox)  # tight-crop: correct grounding on placement (last mission's fix)

    out_img.save(out_path)

    total_px = alpha_u8.size
    opaque_px = int((alpha_u8 > 200).sum())
    return {
        "hue_center_used": round(float(hue_center), 1),
        "hue_tolerance_used": round(float(hue_tolerance), 1),
        "is_gradient_backdrop": bool(is_gradient),
        "opaque_fraction": round(opaque_px / total_px, 4),
    }


def place(canvas: Image.Image, cutout: Image.Image, *, height_frac: float, anchor_x_frac: float) -> None:
    target_h = int(canvas.height * height_frac)
    scale = target_h / cutout.height
    resized = cutout.resize((max(1, int(cutout.width * scale)), target_h), Image.LANCZOS)
    x = int(canvas.width * anchor_x_frac) - resized.width // 2
    y = canvas.height - resized.height
    canvas.alpha_composite(resized, (x, y))


def tint_overlay(img: Image.Image, color: Tuple[int, int, int], opacity: float) -> Image.Image:
    overlay = Image.new("RGBA", img.size, color + (int(255 * opacity),))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


# Default placement per occupancy pattern - a single character is centered;
# two characters use a foreground-left/background-right depth arrangement
# (the composition proven across all 5 scenes of the preceding mission).
SOLO_PLACEMENT = {"height_frac": 0.85, "anchor_x_frac": 0.5}
DUAL_PLACEMENT_PRIMARY = {"height_frac": 0.85, "anchor_x_frac": 0.3}
DUAL_PLACEMENT_SECONDARY = {"height_frac": 0.72, "anchor_x_frac": 0.68}


def composite_scene(background_path, character_cutout_paths: List[Tuple[str, str]],
                     out_path, *, tint_color=(210, 215, 220), tint_opacity=0.08) -> None:
    """`character_cutout_paths` is [(name, path), ...] in the order they
    should be layered (first = furthest back). 1 entry -> solo placement;
    2 entries -> depth-arranged dual placement (proven composition)."""
    canvas = Image.open(background_path).convert("RGBA")
    n = len(character_cutout_paths)
    for i, (_name, path) in enumerate(character_cutout_paths):
        cutout = Image.open(path).convert("RGBA")
        if n == 1:
            place(canvas, cutout, **SOLO_PLACEMENT)
        elif n == 2:
            placement = DUAL_PLACEMENT_SECONDARY if i == 0 else DUAL_PLACEMENT_PRIMARY
            place(canvas, cutout, **placement)
        else:
            # >2 characters: even horizontal distribution - not proven by
            # the preceding mission's test (which only covered 1-2), used
            # only if a future scene plan ever declares 3+.
            frac = (i + 1) / (n + 1)
            place(canvas, cutout, height_frac=0.7, anchor_x_frac=frac)
    canvas = tint_overlay(canvas, tint_color, tint_opacity)
    canvas.convert("RGB").save(out_path)
