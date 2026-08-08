#!/usr/bin/env python3
"""
Sinh icon nguyen ban cho Fanfic Audio Studio -> assets/app_icon.ico

Thiet ke la nguyen ban, don gian, KHONG dung logo/nhan dien cua CapCut hay
bat ky thuong hieu nao:
  - nen bo goc tron, gradient xanh tim (#7C5CFF -> #4C7DFF);
  - mot trang sach mo (van ban) o duoi;
  - mot dai song am (soundwave) mau trang o giua.

Chay lai khi muon doi thiet ke:
    python assets/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "app_icon.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]

ACCENT_TOP = (124, 92, 255)      # #7C5CFF
ACCENT_BOTTOM = (76, 125, 255)   # #4C7DFF
WHITE = (255, 255, 255)
PAGE = (255, 255, 255, 235)
PAGE_LINE = (124, 92, 255, 150)


def rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def gradient(size: int) -> Image.Image:
    """Gradient doc tu tim sang xanh."""
    base = Image.new("RGB", (1, size))
    draw = ImageDraw.Draw(base)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(
            int(ACCENT_TOP[i] + (ACCENT_BOTTOM[i] - ACCENT_TOP[i]) * t) for i in range(3)
        )
        draw.point((0, y), fill=color)
    return base.resize((size, size), Image.Resampling.BILINEAR)


def draw_icon(size: int) -> Image.Image:
    scale = 4  # ve lon roi thu nho lai cho muot
    big = size * scale

    canvas = gradient(big).convert("RGBA")
    canvas.putalpha(rounded_mask(big))
    draw = ImageDraw.Draw(canvas)

    unit = big / 100.0

    # --- trang sach mo o duoi (bieu tuong van ban / truyen)
    # Hai nua trang, canh tren va canh duoi deu chum vao song sach o giua.
    left_page = [
        (19 * unit, 61 * unit),
        (48 * unit, 68 * unit),
        (48 * unit, 88 * unit),
        (19 * unit, 81 * unit),
    ]
    right_page = [
        (52 * unit, 68 * unit),
        (81 * unit, 61 * unit),
        (81 * unit, 81 * unit),
        (52 * unit, 88 * unit),
    ]
    draw.polygon(left_page, fill=PAGE)
    draw.polygon(right_page, fill=PAGE)
    # song sach
    draw.line(
        [(50 * unit, 68.5 * unit), (50 * unit, 87 * unit)],
        fill=PAGE_LINE,
        width=max(1, int(1.6 * unit)),
    )

    # --- dai song am o giua (bieu tuong audio)
    bar_heights = [14, 26, 38, 26, 14]      # % chieu cao
    bar_width = 7.5 * unit
    gap = 4.0 * unit
    total = len(bar_heights) * bar_width + (len(bar_heights) - 1) * gap
    x = (big - total) / 2
    center_y = 33 * unit

    for height_pct in bar_heights:
        half = (height_pct * unit) / 2
        draw.rounded_rectangle(
            [x, center_y - half, x + bar_width, center_y + half],
            radius=bar_width / 2,
            fill=WHITE,
        )
        x += bar_width + gap

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [draw_icon(s) for s in SIZES]
    # Luu .ico nhieu kich thuoc (Windows tu chon size phu hop)
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    # Kem ban PNG 256 de dung cho tai lieu / installer
    frames[-1].save(OUT.with_name("app_icon.png"), format="PNG")
    print(f"Da tao: {OUT} ({OUT.stat().st_size} bytes)")
    print(f"Da tao: {OUT.with_name('app_icon.png')}")


if __name__ == "__main__":
    main()
