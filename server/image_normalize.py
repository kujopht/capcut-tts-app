"""
Chuan hoa anh do NGUOI DUNG tai len o phia MAY CHU — anh dai dien va banner
cua ho so (Social Play V1, capability `profile_banner`).

Module nay la Python THUAN (chi phu thuoc Pillow) — khong FastAPI, khong kho
du lieu, khong mang. Moi ham nhan BYTE va tra ve BYTE (+ metadata), nen chung
kiem thu duoc bang anh dung trong bo nho, khong can dung server nao.

VI SAO CAN MOT LOP RIENG THAY VI TIN CLIENT:

  1. Client co the goi API truc tiep bang curl, boc qua MOI kiem tra o trinh
     duyet — moi rang buoc PHAI cuong che lai o day.
  2. Quyet dinh LOAI ANH bang CACH GIAI MA (Pillow `Image.open()` roi
     `verify()`), khong phai bang duoi tep hay header `Content-Type` nguoi
     dung tu khai — mot tep `.png` co the la JPEG doi ten, hoac khong phai
     anh gi ca.
  3. Anh dong (GIF nhieu khung, WebP animated, PNG APNG) bi TU CHOI: mot anh
     dai dien nhay lien tuc la mot vector spam/gay kho chiu, va viec giai ma
     N khung moi lan hien avatar la mot chi phi khong ai muon tra.
  4. "Bom giai nen" (mot tep vai KB giai ma ra hang ty diem anh) bi chan bang
     tran PIXEL RO RANG truoc khi giai ma toan bo, khong dua vao
     `Image.MAX_IMAGE_PIXELS` mac dinh cua Pillow (con so do co the bi doi o
     noi khac trong tien trinh).
  5. TOAN BO metadata (EXIF/GPS/ICC/XMP) bi XOA truoc khi luu — toa do GPS
     trong mot anh dai dien la mot ro ri vi tri THAT cua nguoi dung.

GIOI HAN (cung xem `/api/limits`):
    avatar   input <= 5 MB,  banner input <= 8 MB
    canh dai nhat cua anh GOC <= 8000 px
    so diem anh DA GIAI MA <= 40 megapixel
    dau ra: avatar  512x512  (cat vuong o giua)
            banner 1500x500  (ti le 3:1, cat "cover" o giua)
    dinh dang dau ra: WebP, chat luong ~85
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image, ImageOps

try:  # Pillow >= 9: hai ten nam o `Image`, khong phai mo-dun rieng.
    _DecompressionBombError = Image.DecompressionBombError
    _DecompressionBombWarning = Image.DecompressionBombWarning
except AttributeError:  # pragma: no cover - Pillow cu hon, khong dung o day.
    from PIL import DecompressionBombError as _DecompressionBombError  # type: ignore
    from PIL import DecompressionBombWarning as _DecompressionBombWarning  # type: ignore


class ImageValidationError(ValueError):
    """Anh khong hop le — thong bao da o dang doc duoc cho nguoi dung."""


#: MIME duoc CHAP NHAN o dau vao, quyet dinh boi Pillow (`Image.format`) SAU
#: khi giai ma — KHONG phai bang duoi tep hay header client gui.
_DINH_DANG_CHO_PHEP = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

#: Canh dai nhat cua anh GOC (truoc khi xu ly), diem anh. Vuot tran bi TU
#: CHOI truoc khi giai ma toan bo pixel — mot anh 20000x20000 header hop le
#: nhung du lieu rac van bi chan o day.
MAX_INPUT_EDGE_PX = 8000

#: So diem anh DA GIAI MA toi da (24 megapixel, vd 6000x4000) — hang rao "bom
#: giai nen" THAT SU (khac `MAX_INPUT_EDGE_PX`, vi mot anh 8000x8000 = 64 MP da
#: vuot tran nay du canh khong vuot rieng le). 24 MP thay vi 40 MP (review bao
#: mat): bo nho giai ma toi da ~96 MB/anh RGBA thay vi ~160 MB. Giao dien da cat
#: san ve 512x512 / 1500x500 truoc khi gui, nen tran nay chi cham nguoi goi API
#: truc tiep bang anh goc rat lon.
MAX_DECODED_PIXELS = 24_000_000

#: Tran KICH THUOC TEP dau vao, byte — theo tung loai.
AVATAR_MAX_INPUT_BYTES = 5 * 1024 * 1024
BANNER_MAX_INPUT_BYTES = 8 * 1024 * 1024

#: Kich thuoc DAU RA.
AVATAR_OUTPUT_SIZE = (512, 512)
BANNER_OUTPUT_SIZE = (1500, 500)          # ti le 3:1

#: Chat luong WebP dau ra.
OUTPUT_WEBP_QUALITY = 85


@dataclass(frozen=True)
class NormalizedImage:
    """Ket qua chuan hoa: san sang de ghi thang xuong kho doi tuong."""

    data: bytes
    mime: str = "image/webp"
    width: int = 0
    height: int = 0

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def _mo_anh_an_toan(raw: bytes, *, max_input_bytes: int) -> Image.Image:
    """
    Giai ma MOT anh tinh (khong hoat hinh), tu choi moi dinh dang/kich thuoc
    khong an toan. Nem `ImageValidationError` voi ly do doc duoc.

    Thu tu BAT BUOC:
      1. kich thuoc TEP THO — tu choi TRUOC khi cham Pillow;
      2. `Image.open()` + `verify()` — phat hien du lieu hong/khong phai anh
         MA KHONG giai ma toan bo pixel;
      3. `Image.open()` LAN HAI (bat buoc sau `verify()`: mot anh da verify
         khong con dung de decode duoc nua — day la hanh vi tai lieu cua
         Pillow, khong phai loi);
      4. kiem dinh dang (`format`), kiem canh, kiem so khung (hoat hinh),
         RIENG kiem tran pixel truoc khi `load()` giai ma that.
    """
    if not raw:
        raise ImageValidationError("Tệp ảnh rỗng.")
    if len(raw) > max_input_bytes:
        mb = max_input_bytes / (1024 * 1024)
        raise ImageValidationError(f"Ảnh vượt quá {mb:.0f} MB.")

    try:
        kiem = Image.open(io.BytesIO(raw))
        kiem.verify()
    except Exception as exc:
        raise ImageValidationError("Ảnh bị hỏng hoặc không đọc được.") from exc

    # `verify()` dong luon tep — phai mo lai de doc du lieu THAT.
    try:
        anh = Image.open(io.BytesIO(raw))
    except Exception as exc:
        raise ImageValidationError("Ảnh bị hỏng hoặc không đọc được.") from exc

    dinh_dang = (anh.format or "").upper()
    if dinh_dang not in _DINH_DANG_CHO_PHEP:
        raise ImageValidationError(
            f"Định dạng ảnh không được hỗ trợ ({anh.format or 'không rõ'}). "
            "Chấp nhận: JPEG, PNG, WebP."
        )

    # Anh DONG (GIF nhieu khung, WebP/PNG hoat hinh) bi tu choi tai day —
    # TRUOC khi giai ma toan bo, vi `n_frames` doc duoc tu HEADER.
    #
    # `getattr(anh, "n_frames", 1)` PHAI duoc GIU LAI trong mot bien roi so
    # sanh — KHONG duoc viet `getattr(anh, "n_frames", 1) and anh.n_frames > 1`:
    # JpegImageFile (va cac dinh dang tinh khac) KHONG co thuoc tinh nay o
    # tat ca (khong phai mot property tra ve 1), nen truy cap TRUC TIEP
    # `anh.n_frames` lan hai se nem `AttributeError` — da bat duoc that (JPEG
    # thuong nem 500 o day).
    so_khung = getattr(anh, "n_frames", 1)
    if so_khung > 1:
        raise ImageValidationError("Không chấp nhận ảnh động (GIF/WebP animation).")

    w, h = anh.size
    if w <= 0 or h <= 0:
        raise ImageValidationError("Ảnh không hợp lệ.")
    if max(w, h) > MAX_INPUT_EDGE_PX:
        raise ImageValidationError(
            f"Cạnh ảnh vượt quá {MAX_INPUT_EDGE_PX}px."
        )
    if w * h > MAX_DECODED_PIXELS:
        raise ImageValidationError(
            f"Ảnh vượt quá {MAX_DECODED_PIXELS // 1_000_000}MP sau khi giải mã."
        )

    # Giai ma THAT SU (buffer/tepstream chi doc header + kich thuoc cho toi
    # day). KHONG doi `Image.MAX_IMAGE_PIXELS` (bien TOAN TIEN TRINH — FastAPI
    # chay handler dong bo tren mot threadpool, nen doi bien nay giua chung
    # se dua request khac trong CUNG tien trinh, va se doi luon hanh vi cua
    # MOI ma khac dung Pillow) va KHONG dung `warnings.catch_warnings()` (CUNG
    # ly do: trang thai bo loc canh bao la toan tien trinh, khong phai theo
    # luong). Phep kiem `w * h > MAX_DECODED_PIXELS` o tren DA chan moi anh
    # vuot han muc cua CHINH TA truoc khi toi day; bat them
    # `DecompressionBombError` o day chi la luoi du phong cho han muc MAC
    # DINH cua Pillow (nguyen ven, khong sua), phong truong hop mot dinh dang
    # nao do bao cao kich thuoc header sai voi du lieu giai ma that.
    try:
        anh.load()
    except _DecompressionBombError as exc:
        raise ImageValidationError("Ảnh quá lớn để giải mã an toàn.") from exc
    except Exception as exc:
        raise ImageValidationError("Ảnh bị hỏng hoặc không đọc được.") from exc

    return anh


def _don_metadata_va_xoay_dung(anh: Image.Image) -> Image.Image:
    """EXIF-transpose (xoay dung chieu THAT theo the EXIF Orientation) roi bo
    HET metadata (EXIF/GPS/ICC/XMP) — `ImageOps.exif_transpose` tra ve mot
    anh MOI khong con the EXIF, va ta khong copy `info` cua anh goc sang.

    BOC trong try/except: mot khoi EXIF HONG (vd the Orientation trai dinh
    dang, offset IFD sai) co the lam `exif_transpose`/`convert` nem
    `struct.error`/`KeyError`/`ValueError` THO — day KHONG duoc phep lot ra
    thanh mot loi 500, vi day van la mot tep NGUOI DUNG tai len."""
    try:
        xoay = ImageOps.exif_transpose(anh)
        if xoay.mode not in ("RGB", "RGBA"):
            xoay = xoay.convert("RGBA" if "A" in xoay.getbands() else "RGB")
        # Anh MOI, khong `info` — cat dut moi ICC profile/XMP con sot trong
        # dict `info` cua doi tuong PIL (mot so duong doc khong xoa het qua
        # convert).
        sach = Image.new(xoay.mode, xoay.size)
        sach.paste(xoay)
        return sach
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("Ảnh bị hỏng hoặc không đọc được.") from exc


def _cat_vuong_giua(anh: Image.Image) -> Image.Image:
    """Cat mot HINH VUONG o CHINH GIUA — dung cho avatar."""
    w, h = anh.size
    canh = min(w, h)
    trai = (w - canh) // 2
    tren = (h - canh) // 2
    return anh.crop((trai, tren, trai + canh, tren + canh))


def _cat_cover_ti_le(anh: Image.Image, ti_le: float) -> Image.Image:
    """
    Cat kieu "cover" (nhu CSS `object-fit: cover`) theo ti le CHO TRUOC
    (rong/cao), giu phan CHINH GIUA — dung cho banner (ti le 3:1).
    """
    w, h = anh.size
    ti_le_hien = w / h
    if ti_le_hien > ti_le:
        # Anh RONG hon ti le muc tieu -> cat hai canh TRAI/PHAI.
        w_moi = int(round(h * ti_le))
        trai = (w - w_moi) // 2
        return anh.crop((trai, 0, trai + w_moi, h))
    if ti_le_hien < ti_le:
        # Anh CAO hon ti le muc tieu -> cat TREN/DUOI.
        h_moi = int(round(w / ti_le))
        tren = (h - h_moi) // 2
        return anh.crop((0, tren, w, tren + h_moi))
    return anh


def _ma_hoa_webp(anh: Image.Image) -> bytes:
    dem = io.BytesIO()
    # WebP khong ho tro RGBA + quality co dinh mot cach dep cho moi truong
    # hop — giu nguyen mode (RGB hoac RGBA), Pillow tu xu ly ca hai.
    anh.save(dem, format="WEBP", quality=OUTPUT_WEBP_QUALITY, method=6)
    return dem.getvalue()


def normalize_avatar(raw: bytes) -> NormalizedImage:
    """Anh dai dien: cat VUONG o giua, resize `AVATAR_OUTPUT_SIZE`, WebP."""
    anh = _mo_anh_an_toan(raw, max_input_bytes=AVATAR_MAX_INPUT_BYTES)
    sach = _don_metadata_va_xoay_dung(anh)
    vuong = _cat_vuong_giua(sach)
    resized = vuong.resize(AVATAR_OUTPUT_SIZE, Image.Resampling.LANCZOS)
    data = _ma_hoa_webp(resized)
    return NormalizedImage(data=data, width=resized.width, height=resized.height)


def normalize_banner(raw: bytes) -> NormalizedImage:
    """Banner ho so: cat COVER ti le 3:1, resize `BANNER_OUTPUT_SIZE`, WebP."""
    anh = _mo_anh_an_toan(raw, max_input_bytes=BANNER_MAX_INPUT_BYTES)
    sach = _don_metadata_va_xoay_dung(anh)
    ti_le = BANNER_OUTPUT_SIZE[0] / BANNER_OUTPUT_SIZE[1]
    cover = _cat_cover_ti_le(sach, ti_le)
    resized = cover.resize(BANNER_OUTPUT_SIZE, Image.Resampling.LANCZOS)
    data = _ma_hoa_webp(resized)
    return NormalizedImage(data=data, width=resized.width, height=resized.height)


def limits_out() -> dict:
    """Hinh dang de ghep vao `GET /api/limits` — xem `server/social.py::mo_ta_gioi_han`."""
    return {
        "avatar_max_input_bytes": AVATAR_MAX_INPUT_BYTES,
        "banner_max_input_bytes": BANNER_MAX_INPUT_BYTES,
        "max_input_edge_px": MAX_INPUT_EDGE_PX,
        "max_decoded_megapixels": MAX_DECODED_PIXELS // 1_000_000,
        "avatar_output_size": list(AVATAR_OUTPUT_SIZE),
        "banner_output_size": list(BANNER_OUTPUT_SIZE),
        "accepted_mime": list(_DINH_DANG_CHO_PHEP.values()),
    }
