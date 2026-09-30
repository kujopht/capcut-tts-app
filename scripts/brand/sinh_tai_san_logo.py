"""
Sinh bo tai san thuong hieu Fanfic World tu HAI anh goc chu du an da chon.

  Anh 1 (icon vuong bo goc, nen trang)  -> favicon.ico, icon-*.png, maskable,
                                            apple-icon.png, du lieu BrandMark (OG)
  Anh 2 (bieu tuong + chu, nen trang)   -> logo-emblem.webp, logo-wordmark.webp
                                            (chu "fanfic" doi sang mau sang cho
                                            nen toi, ".world" nang do sang)

Anh goc KHONG nam trong kho (chu du an giu). Chay lai khi doi anh:

    .\\.venv\\Scripts\\python.exe scripts/brand/sinh_tai_san_logo.py \\
        --icon <anh_1.png> --logo <anh_2.png> --web web [--xem <thu_muc_xem_truoc>]

Sau khi chay: kiem bang mat cac anh xem truoc (nen toi + nen trang, 16px phong
to), roi `npm test` — `web/tests/ui.test.mjs` khoa kich thuoc, do trong suot va
ti le width/height trong `components/Logo.tsx`.
"""
from __future__ import annotations

import argparse
import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

# Dat tu dong lenh trong `main()`.
ANH_1 = Path()
ANH_2 = Path()

NEN_WEB = (8, 9, 15)          # --bg cua globals.css (#08090f)
CHU_SANG = (241, 242, 251)    # gan --text (#eceff7), hoi ngả lavender
NANG_WORLD = 0.22             # nang do sang ".world" 22% quang duong toi trang


def lum(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def nen_trang_noi_bien(rgb: np.ndarray, nguong: float) -> np.ndarray:
    """Mat na nen: diem gan trang NOI voi mep anh (flood fill tu moi mep)."""
    h, w, _ = rgb.shape
    gan_trang = (lum(rgb) > nguong) & (rgb.min(axis=2) > nguong - 25)
    m = Image.fromarray(np.where(gan_trang, 255, 0).astype(np.uint8), "L")
    # Dong khung 1px trang quanh anh de mot lan floodfill phu het moi mep.
    khung = Image.new("L", (w + 2, h + 2), 255)
    khung.paste(m, (1, 1))
    ImageDraw.floodfill(khung, (0, 0), 128, thresh=0)
    return np.array(khung)[1:-1, 1:-1] == 128


def co_mat_na(mask: np.ndarray, px: int) -> np.ndarray:
    """Co (erode) mat na `px` diem anh."""
    im = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    for _ in range(px):
        im = im.filter(ImageFilter.MinFilter(3))
    return np.array(im) > 127


def gian_mat_na(mask: np.ndarray, px: int) -> np.ndarray:
    im = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), "L")
    for _ in range(px):
        im = im.filter(ImageFilter.MaxFilter(3))
    return np.array(im) > 127


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def luu_png(im: Image.Image, p: Path) -> int:
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, "PNG", optimize=True)
    return p.stat().st_size


def luu_webp(im: Image.Image, p: Path) -> int:
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, "WEBP", quality=92, method=6, alpha_quality=100)
    return p.stat().st_size


def tren_nen(im: Image.Image, mau=NEN_WEB, pad=0, phong=1) -> Image.Image:
    """Dat RGBA len nen web de xem truoc, phong to `phong` lan (NEAREST)."""
    w, h = im.size
    nen = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), mau + (255,))
    nen.alpha_composite(im, (pad, pad))
    if phong != 1:
        nen = nen.resize((nen.width * phong, nen.height * phong), Image.NEAREST)
    return nen.convert("RGB")


# ----------------------------------------------------------------- anh 1


def icon_bo_goc() -> Image.Image:
    """Anh 1 -> RGBA vuong: o bo goc, ngoai o trong suot, bo vien nhieu trang."""
    rgb = np.array(Image.open(ANH_1).convert("RGB"))
    nen = nen_trang_noi_bien(rgb, 215)
    o = ~nen
    # Co 3px: cat dai khu rang cua trang tron voi mep o (se thanh vien sang
    # tren nen toi neu giu lai).
    o = co_mat_na(o, 3)
    x0, y0, x1, y1 = bbox(o)
    canh = max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x0, y0 = int(round(cx - canh / 2)), int(round(cy - canh / 2))
    rgba = np.dstack([rgb, np.where(o, 255, 0).astype(np.uint8)])
    im = Image.fromarray(rgba, "RGBA").crop((x0, y0, x0 + canh, y0 + canh))
    # Khu rang cua mat na: lam mem 1px o do phan giai goc.
    a = im.getchannel("A").filter(ImageFilter.GaussianBlur(0.8))
    im.putalpha(a)
    print(f"[anh1] o bo goc {canh}x{canh} tai ({x0},{y0})")
    return im


#: Mau long o sat mep (navy) — nen phu kin tron vao day.
NAVY_LONG = (22, 18, 72)


def long_o(icon: Image.Image, canh: int, bo: float) -> Image.Image:
    """
    Long o, bo di vien sang (`bo` x canh), mep lam mem — RGBA da nhan truoc
    voi nen navy nen lam mo KHONG keo mau trang cua diem trong suot vao.
    """
    nho = icon.resize((canh, canh), Image.LANCZOS)
    a = np.array(nho.getchannel("A")) > 127
    a = co_mat_na(a, max(2, int(canh * bo)))
    mem = Image.fromarray(np.where(a, 255, 0).astype(np.uint8), "L").filter(
        ImageFilter.GaussianBlur(canh * 0.035))
    phang = Image.new("RGB", (canh, canh), NAVY_LONG)
    phang.paste(nho.convert("RGB"), (0, 0), mem)
    ket = phang.convert("RGBA")
    ket.putalpha(mem)
    return ket


def nen_tran_vien(icon: Image.Image, canh: int) -> Image.Image:
    """
    Nen PHU KIN (khong trong suot): gradient song tuyen tu MAU NEN cua long o,
    lay mau o bon goc trong (15% vao trong, trung binh mot o 8%) — khong lay
    tu noi dung (sach/sao) nen mep canvas khong co vet sang.
    """
    rgb = np.array(icon.convert("RGB")).astype(np.float64)
    n = icon.width
    r = int(n * 0.04)

    def mau(fx: float, fy: float) -> np.ndarray:
        x, y = int(n * fx), int(n * fy)
        vung = rgb[y - r:y + r, x - r:x + r].reshape(-1, 3)
        # Bo diem sang (sao nho) truoc khi lay trung binh.
        return np.median(vung[lum(vung) < np.percentile(lum(vung), 70)], axis=0)

    tl, tr, bl, br = mau(0.15, 0.15), mau(0.85, 0.15), mau(0.15, 0.85), mau(0.85, 0.85)
    t = np.linspace(0, 1, canh)[None, :, None]
    s = np.linspace(0, 1, canh)[:, None, None]
    luoi = (tl * (1 - t) + tr * t) * (1 - s) + (bl * (1 - t) + br * t) * s
    print(f"[nen] goc: {tl.round()} {tr.round()} {bl.round()} {br.round()}")
    return Image.fromarray(luoi.round().astype(np.uint8), "RGB").convert("RGBA")


def icon_phu_kin(icon: Image.Image, canh: int, ti_le: float) -> Image.Image:
    """
    Icon khong trong suot cho apple-touch-icon / maskable: noi dung o chiem
    `ti_le` canh canvas, bo vien sang cua o, mep hoa vao nen tran vien.
    """
    nen = nen_tran_vien(icon, canh)
    s = int(round(canh * ti_le))
    nho = long_o(icon, s, 0.055)
    lech = (canh - s) // 2
    nen.alpha_composite(nho, (lech, lech))
    return nen


#: Favicon nho: cat sat long o (ti le, dich xuong) de sao + sach du to khi con
#: 16-48px; da so sanh bang mat tren nen toi va nen trang (icon16_bien_the.png).
CAT_NHO = {16: (0.72, 0.03, 1.25, 80), 32: (0.86, 0.015, 1.0, 60), 48: (0.90, 0.01, 1.0, 50)}


def icon_nho(icon: Image.Image, canh: int) -> Image.Image:
    if canh not in CAT_NHO:
        return icon.resize((canh, canh), Image.LANCZOS)
    ti_le, dich_y, tang, sac = CAT_NHO[canh]
    goc = icon.width
    s = int(goc * ti_le)
    x0 = (goc - s) // 2
    y0 = int((goc - s) // 2 + dich_y * goc)
    long = icon.convert("RGB").crop((x0, y0, x0 + s, y0 + s)).resize((goc, goc), Image.LANCZOS)
    # Giu dung hinh o bo goc cua ban goc, chi phong to phan long.
    a = icon.getchannel("A").resize((canh, canh), Image.LANCZOS)
    rgb = long.resize((canh * 4, canh * 4), Image.LANCZOS).resize((canh, canh), Image.BOX)
    if tang != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(tang)
        rgb = ImageEnhance.Color(rgb).enhance(1.15)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=sac, threshold=1))
    im = rgb.convert("RGBA")
    im.putalpha(a)
    return im


# ----------------------------------------------------------------- anh 2


def logo_tach_nen() -> tuple[Image.Image, Image.Image]:
    """Anh 2 -> (bieu tuong RGBA, chu RGBA da doi mau cho nen toi)."""
    rgb = np.array(Image.open(ANH_2).convert("RGB")).astype(np.float64)
    nen = nen_trang_noi_bien(rgb.astype(np.uint8), 228)
    fg = ~nen
    # Dai khu rang cua: diem tien canh sat nen -> "color to alpha" voi mau trang.
    dai = fg & gian_mat_na(nen, 3)
    alpha = np.where(fg, 1.0, 0.0)
    a_dai = ((255.0 - rgb) / 255.0).max(axis=2)
    alpha = np.where(dai, np.clip(a_dai, 0, 1), alpha)
    mau = rgb.copy()
    an_toan = np.maximum(alpha, 1e-6)[..., None]
    mau_dai = np.clip((rgb - (1 - alpha[..., None]) * 255.0) / an_toan, 0, 255)
    mau = np.where(dai[..., None], mau_dai, mau)
    rgba = np.dstack([mau, alpha * 255.0]).round().astype(np.uint8)

    # Tach bieu tuong / chu theo khoang hang trong lon nhat.
    hang = (rgba[..., 3] > 20).any(axis=1)
    ys = np.nonzero(hang)[0]
    khoang = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1) if ys[i + 1] - ys[i] > 1]
    tren, duoi = max(khoang, key=lambda k: k[1] - k[0])
    print(f"[anh2] khoang trong giua bieu tuong va chu: hang {tren}..{duoi}")

    def cat(y0: int, y1: int) -> np.ndarray:
        phan = rgba[y0:y1].copy()
        x0, yy0, x1, yy1 = bbox(phan[..., 3] > 8)
        return phan[yy0:yy1, x0:x1]

    bieu_tuong = cat(0, tren + 1)
    chu = cat(duoi, rgba.shape[0])

    # "fanfic" (xanh navy dam) -> mau sang. ".world" giu gradient. Ranh gioi la
    # dau cham tim: cot dau tien co diem sang + bao hoa cao.
    c = chu.astype(np.float64)
    L = lum(c)
    bao_hoa = c[..., :3].max(axis=2) - c[..., :3].min(axis=2)
    world = (c[..., 3] > 150) & (L > 75) & (bao_hoa > 60)
    cot = np.nonzero(world.any(axis=0))[0]
    x_cham = int(cot.min())
    print(f"[anh2] chu {chu.shape[1]}x{chu.shape[0]}, '.world' bat dau o cot {x_cham}")
    fanfic = np.zeros(chu.shape[:2], bool)
    fanfic[:, : x_cham - 2] = True
    chu[fanfic, 0], chu[fanfic, 1], chu[fanfic, 2] = CHU_SANG

    # ".world": giu SAC (hue) gradient tim -> xanh cua ban goc, chi nang do
    # sang de con doc duoc tren nen toi o co chu nho (footer ~16px).
    phan = chu[:, x_cham - 2:, :3].astype(np.float64) / 255.0
    mx, mn = phan.max(axis=2), phan.min(axis=2)
    l = (mx + mn) / 2
    l_moi = np.minimum(1.0, l + NANG_WORLD * (1 - l))
    # Dich deu moi kenh quanh trung diem theo ti le giu nguyen do bao hoa tuong doi.
    he_so = np.where(l > 1e-6, l_moi / np.maximum(l, 1e-6), 1.0)
    moi = np.clip(phan * he_so[..., None], 0, 1)
    chu[:, x_cham - 2:, :3] = (moi * 255).round().astype(np.uint8)
    c = chu.astype(np.float64)
    L = lum(c)
    bao_hoa = c[..., :3].max(axis=2) - c[..., :3].min(axis=2)
    world = (c[..., 3] > 150) & (L > 75) & (bao_hoa > 60)

    # Do tuong phan ".world" tren nen web.
    def rl(v):
        v = v / 255.0
        return np.where(v <= 0.03928, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)

    px = c[world][:, :3]
    Lw = 0.2126 * rl(px[:, 0]) + 0.7152 * rl(px[:, 1]) + 0.0722 * rl(px[:, 2])
    Lb = 0.2126 * rl(np.array(NEN_WEB[0])) + 0.7152 * rl(np.array(NEN_WEB[1])) + 0.0722 * rl(np.array(NEN_WEB[2]))
    tp = (Lw + 0.05) / (Lb + 0.05)
    print(f"[anh2] tuong phan '.world' / nen: p5={np.percentile(tp, 5):.2f} trung vi={np.median(tp):.2f}")

    return Image.fromarray(bieu_tuong, "RGBA"), Image.fromarray(chu, "RGBA")


def theo_cao(im: Image.Image, cao: int) -> Image.Image:
    w = int(round(im.width * cao / im.height))
    return im.resize((w, cao), Image.LANCZOS)


def ghep_ico(anh: list[Image.Image], p: Path) -> int:
    """ICO nhieu kich thuoc, moi muc la PNG (Vista+) — giu dung pixel da tinh chinh."""
    muc = []
    for im in anh:
        b = io.BytesIO()
        im.save(b, "PNG", optimize=True)
        muc.append((im.width, im.height, b.getvalue()))
    dau = 6 + 16 * len(muc)
    out = io.BytesIO()
    out.write((0).to_bytes(2, "little") + (1).to_bytes(2, "little") + len(muc).to_bytes(2, "little"))
    vi_tri = dau
    for w, h, data in muc:
        out.write(bytes([w % 256, h % 256, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little"))
        out.write(len(data).to_bytes(4, "little") + vi_tri.to_bytes(4, "little"))
        vi_tri += len(data)
    for _, _, data in muc:
        out.write(data)
    p.write_bytes(out.getvalue())
    return p.stat().st_size


def main() -> None:
    global ANH_1, ANH_2
    ap = argparse.ArgumentParser(description="Sinh favicon/icon/logo Fanfic World tu hai anh goc.")
    ap.add_argument("--icon", required=True, type=Path, help="anh 1: icon vuong bo goc, nen trang")
    ap.add_argument("--logo", required=True, type=Path, help="anh 2: bieu tuong + chu, nen trang")
    ap.add_argument("--web", required=True, type=Path, help="thu muc web/ cua kho")
    ap.add_argument("--xem", type=Path, help="thu muc ghi anh xem truoc (tuy chon)")
    a = ap.parse_args()
    ANH_1, ANH_2, web = a.icon, a.logo, a.web
    brand = web / "public" / "brand"
    app = web / "src" / "app"
    kq: dict[str, int] = {}

    # ---- anh 1
    icon = icon_bo_goc()
    nho = {s: icon_nho(icon, s) for s in (16, 32, 48)}
    for s in (16, 32, 48, 192, 512):
        im = nho.get(s) or icon_nho(icon, s)
        kq[f"public/brand/icon-{s}.png"] = luu_png(im, brand / f"icon-{s}.png")
    kq["src/app/favicon.ico"] = ghep_ico([nho[16], nho[32], nho[48]], app / "favicon.ico")
    maskable = icon_phu_kin(icon, 512, 0.78).convert("RGB")
    kq["public/brand/icon-maskable-512.png"] = luu_png(maskable, brand / "icon-maskable-512.png")
    apple = icon_phu_kin(icon, 180, 1.0).convert("RGB")
    kq["src/app/apple-icon.png"] = luu_png(apple, app / "apple-icon.png")

    # BrandMark cho anh Open Graph (Satori): PNG nhung thang, khong doc tep luc chay.
    og = icon.resize((208, 208), Image.LANCZOS).quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    b = io.BytesIO()
    og.save(b, "PNG", optimize=True)
    du_lieu = base64.b64encode(b.getvalue()).decode("ascii")
    ts = web / "src" / "components" / "brandMarkData.ts"
    ts.write_text(
        "/**\n"
        " * Bieu tuong Fanfic World (o bo goc) dang PNG 208x208, nhung thang de\n"
        " * `ImageResponse` (Satori) dung ma khong doc tep luc chay tren Worker.\n"
        " * SINH TU DONG tu anh icon goc — khong sua tay.\n"
        " */\n"
        f'export const BRAND_MARK_PNG =\n  "data:image/png;base64,{du_lieu}";\n',
        encoding="utf-8",
    )
    kq["src/components/brandMarkData.ts"] = ts.stat().st_size

    # ---- anh 2
    bieu_tuong, chu = logo_tach_nen()
    kq["public/brand/logo-emblem.webp"] = luu_webp(theo_cao(bieu_tuong, 160), brand / "logo-emblem.webp")
    kq["public/brand/logo-wordmark.webp"] = luu_webp(theo_cao(chu, 96), brand / "logo-wordmark.webp")
    for k, v in kq.items():
        print(f"  {k}: {v:,} byte")

    if a.xem is None:
        return
    xem = a.xem
    xem.mkdir(parents=True, exist_ok=True)
    # Ban xep chong day du — chi de xem truoc, chua noi nao trong web dung toi.
    rong = max(bieu_tuong.width, chu.width)
    cach = int(bieu_tuong.height * 0.08)
    full = Image.new("RGBA", (rong, bieu_tuong.height + cach + chu.height), (0, 0, 0, 0))
    full.alpha_composite(bieu_tuong, ((rong - bieu_tuong.width) // 2, 0))
    full.alpha_composite(chu, ((rong - chu.width) // 2, bieu_tuong.height + cach))

    # ---- xem truoc tren nen web
    tren_nen(nho[16], pad=4, phong=8).save(xem / "icon16_x8.png")
    tren_nen(nho[32], pad=4, phong=6).save(xem / "icon32_x6.png")
    tren_nen(nho[16], mau=(255, 255, 255), pad=4, phong=8).save(xem / "icon16_x8_sang.png")
    tren_nen(icon_nho(icon, 192), pad=16).save(xem / "icon192.png")
    maskable.save(xem / "maskable512.png")
    # Mo phong mat na tron cua Android + vung an toan 80%.
    m = maskable.convert("RGBA")
    tron = Image.new("L", m.size, 0)
    ImageDraw.Draw(tron).ellipse((0, 0, 511, 511), fill=255)
    m.putalpha(tron)
    ve = ImageDraw.Draw(m)
    ve.ellipse((51, 51, 460, 460), outline=(255, 80, 80, 255), width=2)
    tren_nen(m, mau=(240, 240, 240), pad=10).save(xem / "maskable_tron.png")
    apple.resize((360, 360), Image.LANCZOS).save(xem / "apple180_x2.png")
    tren_nen(theo_cao(bieu_tuong, 34 * 2), pad=12).save(xem / "emblem68.png")
    tren_nen(theo_cao(chu, 22 * 2), pad=12).save(xem / "wordmark44.png")
    tren_nen(theo_cao(full, 300), pad=20).save(xem / "full300.png")


if __name__ == "__main__":
    main()
