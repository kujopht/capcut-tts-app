"""Deterministic scene-occupancy and identity verification.

This module never trusts prompt text alone (per mission requirement 2:
"Do not rely only on prompt instructions"). Every check here operates on
actual pixels of the generated layer, using only numpy/PIL (no ML model,
no new paid provider - scipy is not installed in this environment and is
not added; connected-component labeling is implemented directly).

Two real, disclosed limitations (not hidden):
- Person-COUNTING is done via connected-component blob analysis on the
  chroma-keyed alpha mask, not a real person-detector. A single character
  whose limbs are genuinely disconnected in the artwork (e.g. an arm
  fully separated from the torso by background showing through) could
  under-count; two overlapping/touching figures could under-count as one
  blob. This is a real, honest limitation of a zero-new-dependency
  approach - it catches the failure modes actually observed in this
  session's manual review (a clearly separate extra figure, a clearly
  separate stray artifact), not every conceivable case.
- Identity-drift detection compares dominant hair-region hue against the
  canonical reference's hair-region hue. This is a real, deterministic
  color-based heuristic, not a face-embedding/similarity model - it
  catches gross drift (e.g. the wrong hair color, the wrong outfit color
  family) of the kind actually observed in the layered-composition
  mission's predecessor (one-pass dual-character) run, not subtle
  facial-structure drift.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple  # noqa: F401 - Optional used below

import numpy as np
from PIL import Image


class FailureType(str, Enum):
    IDENTITY_DRIFT = "IDENTITY_DRIFT"
    EXTRA_PERSON = "EXTRA_PERSON"
    MISSING_PERSON = "MISSING_PERSON"
    COMPOSITION_FAIL = "COMPOSITION_FAIL"
    GENERATION_FAIL = "GENERATION_FAIL"
    QA_FAIL = "QA_FAIL"


@dataclass
class OccupancyResult:
    ok: bool
    blob_count: int
    blob_area_fractions: List[float]
    failure: Optional[FailureType] = None
    detail: str = ""


@dataclass
class IdentityResult:
    ok: bool
    hue_distance: float
    reference_hue: float
    candidate_hue: float
    failure: Optional[FailureType] = None
    detail: str = ""


def _connected_components(mask: np.ndarray, *, min_area_fraction: float = 0.01) -> List[int]:
    """Pure numpy/collections connected-component sizes (4-connectivity),
    via BFS on a downsampled boolean mask - no scipy dependency. Returns
    the AREA (in downsampled-pixel count, as a fraction of total) of every
    component at least `min_area_fraction` of the image, largest first.
    """
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    total = h * w
    areas: List[int] = []

    for y in range(h):
        row = mask[y]
        for x in range(w):
            if row[x] and not visited[y, x]:
                # BFS flood-fill of this component
                q = deque([(y, x)])
                visited[y, x] = True
                area = 0
                while q:
                    cy, cx = q.popleft()
                    area += 1
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            q.append((ny, nx))
                areas.append(area)

    areas.sort(reverse=True)
    min_area = int(total * min_area_fraction)
    return [a for a in areas if a >= min_area]


def verify_solo_occupancy(rgba_cutout_path, *, downsample_to: int = 220,
                            min_area_fraction: float = 0.015,
                            max_canvas_fill_fraction: Optional[float] = 0.62,
                            min_bbox_fill_ratio: Optional[float] = 0.15) -> OccupancyResult:
    # min_bbox_fill_ratio lowered from an initial 0.22 to 0.15 after real
    # batch-proof data (Job 3/Sakura): a long-flowing-hair character design
    # legitimately measured 21.2% on an otherwise-correct, coherent
    # extraction - long hair strands create real negative space within the
    # bounding box that a compact character (Naruto/Sasuke) doesn't have.
    # Still well above the genuinely-shattered cases observed (3.5%, 5.0%,
    # 6.9%), so this keeps real fragmentation detection while not penalizing
    # a legitimate hair-heavy silhouette.
    """A layer generated as a SOLO character must contain exactly one
    foreground blob once chroma-keyed - AND that blob must actually look
    like a coherent character silhouette, not a malformed extraction.

    Two real, previously-MISSING checks added here after a real batch-
    proof failure this mission (Job 3/Sakura): blob-COUNT alone let two
    genuinely broken extractions through undetected -
    (a) a chroma-key that barely keyed anything, leaving almost the WHOLE
        canvas as one giant "opaque" blob (the background never got
        removed at all) - caught by `max_canvas_fill_fraction`: a real
        character silhouette should occupy a MINORITY of its own canvas,
        not nearly all of it;
    (b) a chroma-key that shattered the character into scattered
        "confetti" fragments loosely bridged into one nominally-connected
        blob - caught by `min_bbox_fill_ratio`: the largest blob's opaque
        pixel count relative to its OWN bounding-box area should be
        reasonably high for a real, solid silhouette; a low ratio means
        the "blob" is mostly holes, i.e. malformed (FailureType.
        COMPOSITION_FAIL, per the mission's explicit "malformed layer/
        composite" retry trigger).

    Pass `max_canvas_fill_fraction=None` and/or `min_bbox_fill_ratio=None`
    to skip those two checks - needed for REFERENCE portraits, which are
    never meant to have a clean, keyable solid backdrop in the first place
    (a real design mismatch discovered live in this mission's own second
    batch-job retry: applying the scene-layer fill-ratio checks to
    reference portraits produced false rejections of genuinely correct,
    single-person portraits whose background was merely textured/gradient,
    not because they had a real occupancy problem)."""
    img = Image.open(rgba_cutout_path).convert("RGBA")
    # Downsample for tractable pure-Python BFS - a full 1024x1536 mask is
    # ~1.6M pixels; a ~220px-wide version preserves blob-separation
    # structure (which is what this check needs) at a fraction of the cost.
    scale = downsample_to / max(img.size)
    small = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.NEAREST)
    alpha = np.asarray(small)[..., 3]
    mask = alpha > 127

    areas = _connected_components(mask, min_area_fraction=min_area_fraction)
    total_px = mask.size
    fractions = [a / total_px for a in areas]

    if len(areas) == 0:
        return OccupancyResult(ok=False, blob_count=0, blob_area_fractions=[],
                                failure=FailureType.MISSING_PERSON,
                                detail="No foreground blob found above the area threshold - "
                                       "the character may have failed to render or the "
                                       "chroma-key over-keyed the whole image.")
    if len(areas) > 1:
        return OccupancyResult(ok=False, blob_count=len(areas), blob_area_fractions=fractions,
                                failure=FailureType.EXTRA_PERSON,
                                detail=f"{len(areas)} disjoint foreground blobs found in a "
                                       f"solo-character layer (areas: {[round(f, 3) for f in fractions]}) - "
                                       f"expected exactly 1.")

    if max_canvas_fill_fraction is not None and fractions[0] > max_canvas_fill_fraction:
        return OccupancyResult(ok=False, blob_count=1, blob_area_fractions=fractions,
                                failure=FailureType.COMPOSITION_FAIL,
                                detail=f"The single foreground blob fills {fractions[0]:.1%} of the "
                                       f"canvas (limit {max_canvas_fill_fraction:.0%}) - the chroma-key "
                                       f"likely failed to remove most of the backdrop (malformed layer).")

    if min_bbox_fill_ratio is not None:
        ys, xs = np.where(mask)
        bbox_area = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
        bbox_fill_ratio = areas[0] / bbox_area if bbox_area else 0.0
        if bbox_fill_ratio < min_bbox_fill_ratio:
            return OccupancyResult(ok=False, blob_count=1, blob_area_fractions=fractions,
                                    failure=FailureType.COMPOSITION_FAIL,
                                    detail=f"The foreground blob only fills {bbox_fill_ratio:.1%} of its "
                                           f"own bounding box (limit {min_bbox_fill_ratio:.0%}) - likely a "
                                           f"shattered/fragmented chroma-key extraction, not a coherent "
                                           f"character silhouette (malformed layer).")

    return OccupancyResult(ok=True, blob_count=1, blob_area_fractions=fractions)


def _hue_of_rgb_pixels(rgb: np.ndarray) -> float:
    if len(rgb) == 0:
        return float("nan")
    r, g, b = rgb.mean(axis=0)
    maxc, minc = max(r, g, b), min(r, g, b)
    delta = maxc - minc + 1e-8
    if maxc == r:
        hue = 60 * (((g - b) / delta) % 6)
    elif maxc == g:
        hue = 60 * (((b - r) / delta) + 2)
    else:
        hue = 60 * (((r - g) / delta) + 4)
    return float(hue)


def _sample_hair_region_hue_cutout(rgba_cutout_path) -> float:
    """Sample the dominant hue in the top-center portion of a character
    cutout's ALPHA bounding box - the region most likely to be hair, not
    skin/clothing/leftover background. Real bug fixed here: an EARLIER
    version sampled the full-WIDTH top band of the bbox, which picked up
    leaked corner/edge background pixels whenever chroma-keying left a
    residual two-tone or gradient backdrop (observed live in this
    mission's own first batch-job run: a correctly-identical Naruto
    render was falsely flagged as drifted because the untouched teal/
    green backdrop corners dominated the top band's average hue). Also
    restricting to the horizontal CENTER of the bbox - dynamic action
    poses can place an outstretched arm/leg at the very top of the
    bounding box instead of the head, so this additionally requires the
    top-center region to be small relative to the whole bbox (a real
    head/hair silhouette, not a limb) and falls back to a slightly taller
    band if the tight one has too few opaque pixels to be reliable."""
    img = Image.open(rgba_cutout_path).convert("RGBA")
    arr = np.asarray(img)
    alpha = arr[..., 3]
    ys, xs = np.where(alpha > 127)
    if len(ys) == 0:
        return float("nan")
    top, bottom = ys.min(), ys.max()
    left, right = xs.min(), xs.max()
    height = bottom - top
    width = right - left

    for band_frac, center_frac, min_px in ((0.18, 0.36, 400), (0.30, 0.5, 200)):
        band_bottom = top + max(1, int(height * band_frac))
        cx_lo = left + int(width * (0.5 - center_frac / 2))
        cx_hi = left + int(width * (0.5 + center_frac / 2))
        yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
        band_mask = (alpha > 127) & (yy >= top) & (yy <= band_bottom) & (xx >= cx_lo) & (xx <= cx_hi)
        rgb = arr[..., :3][band_mask].astype(np.float32) / 255.0
        if len(rgb) >= min_px:
            return _hue_of_rgb_pixels(rgb)
    return float("nan")


def _sample_hair_region_hue_portrait(portrait_path) -> float:
    """Reference portraits (ensure_references()) are flat OPAQUE renders
    (no real alpha) on a consistent "front-facing, waist-up" composition -
    an alpha-bbox approach would just select the whole opaque canvas. This
    samples a fixed top-center crop instead, since the framing is always
    the same by construction (the same prompt template every time)."""
    img = Image.open(portrait_path).convert("RGB")
    w, h = img.size
    x0, x1 = int(w * 0.30), int(w * 0.70)
    y0, y1 = int(h * 0.05), int(h * 0.28)
    arr = np.asarray(img.crop((x0, y0, x1, y1))).astype(np.float32) / 255.0
    return _hue_of_rgb_pixels(arr.reshape(-1, 3))


def verify_identity(candidate_cutout_path, reference_portrait_path, *,
                     reference_proxy_cutout_path=None,
                     max_hue_distance: float = 55.0) -> IdentityResult:
    # Calibrated from real data, not guessed: a confirmed-correct blond-hair
    # render (verified by eye) measured 43.5 degrees of hue drift from its
    # own reference purely from anime cel-shading/lighting variance within
    # the "blond" family - a 40 degree tolerance produced a false positive.
    # A genuine cross-character mismatch (Naruto vs Sasuke, prior mission)
    # measured 173.6 degrees - 55 degrees stays far below that real signal
    # while giving blond-family shading room to vary.
    """Compare the candidate character layer's hair-region hue against the
    canonical reference portrait's hair-region hue. See module docstring
    for this check's real, disclosed limitations.

    Real bug fixed here: the reference-portrait sample used a blind fixed-
    fraction crop (top 5-28% height, center 30-70% width), assuming hair is
    always there - observed to fail for real on a portrait whose framing
    put an accessory (a forehead gem) in that exact band instead of hair,
    producing a spurious reference hue and a false IDENTITY_DRIFT. When a
    `reference_proxy_cutout_path` is available (a chroma-keyed proxy of the
    SAME reference, already computed once for its own occupancy check in
    ensure_references()), the adaptive alpha-bbox sampler used for real
    scene-layer cutouts is reused for the reference too, instead of the
    blind crop."""
    if reference_proxy_cutout_path:
        ref_hue = _sample_hair_region_hue_cutout(reference_proxy_cutout_path)
    else:
        ref_hue = _sample_hair_region_hue_portrait(reference_portrait_path)
    cand_hue = _sample_hair_region_hue_cutout(candidate_cutout_path)
    if ref_hue != ref_hue or cand_hue != cand_hue:  # NaN check
        return IdentityResult(ok=False, hue_distance=float("nan"), reference_hue=ref_hue,
                               candidate_hue=cand_hue, failure=FailureType.QA_FAIL,
                               detail="Could not sample a hair-region hue from one of the images "
                                      "(no opaque pixels found) - treat as a QA failure, not a pass.")
    dist = min(abs(ref_hue - cand_hue), 360 - abs(ref_hue - cand_hue))
    if dist > max_hue_distance:
        return IdentityResult(ok=False, hue_distance=dist, reference_hue=ref_hue,
                               candidate_hue=cand_hue, failure=FailureType.IDENTITY_DRIFT,
                               detail=f"Hair-region hue drifted {dist:.1f} degrees from the "
                                      f"canonical reference (ref={ref_hue:.1f}, "
                                      f"candidate={cand_hue:.1f}), exceeding the "
                                      f"{max_hue_distance} degree tolerance.")
    return IdentityResult(ok=True, hue_distance=dist, reference_hue=ref_hue, candidate_hue=cand_hue)
