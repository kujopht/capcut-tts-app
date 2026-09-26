"""
Kiem thu `server/image_normalize.py` — chuan hoa anh dai dien/banner o may chu.

Moi anh duoc TAO trong bo nho bang Pillow, khong doc tep tren dia — bo test
nay khong can tai nguyen ben ngoai.
"""

from __future__ import annotations

import io
import unittest

from PIL import Image

from server.image_normalize import (
    AVATAR_MAX_INPUT_BYTES,
    ImageValidationError,
    MAX_DECODED_PIXELS,
    MAX_INPUT_EDGE_PX,
    limits_out,
    normalize_avatar,
    normalize_banner,
)


def _png(size=(300, 200), mode="RGB", color=(10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(size=(300, 200), color=(200, 100, 50), **save_kwargs) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", **save_kwargs)
    return buf.getvalue()


def _webp(size=(300, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (5, 5, 5)).save(buf, format="WEBP")
    return buf.getvalue()


def _jpeg_with_exif_orientation(size=(300, 200), orientation=6) -> bytes:
    """JPEG kem the EXIF Orientation (xoay 90 do) — dai dien cho truong hop
    'anh dien thoai chup doc bi luu ngang, EXIF ghi lai huong that'."""
    img = Image.new("RGB", size, (200, 100, 50))
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _animated_gif() -> bytes:
    khung = [Image.new("RGB", (50, 50), (i * 40, 0, 0)) for i in range(3)]
    buf = io.BytesIO()
    khung[0].save(buf, format="GIF", save_all=True, append_images=khung[1:],
                 duration=100, loop=0)
    return buf.getvalue()


class ChuanHoaAvatarTest(unittest.TestCase):
    def test_png_hop_le_ra_webp_vuong(self):
        ket = normalize_avatar(_png(size=(400, 200)))
        self.assertEqual(ket.mime, "image/webp")
        self.assertEqual((ket.width, ket.height), (512, 512))
        # Giai ma lai de chac chan la WebP THAT, khong phai chi doi ten.
        lai = Image.open(io.BytesIO(ket.data))
        self.assertEqual(lai.format, "WEBP")

    def test_jpeg_hop_le_thanh_cong(self):
        ket = normalize_avatar(_jpeg())
        self.assertEqual(ket.mime, "image/webp")

    def test_webp_hop_le_thanh_cong(self):
        ket = normalize_avatar(_webp())
        self.assertEqual(ket.mime, "image/webp")

    def test_jpeg_doi_ten_thanh_png_van_bi_nhan_dung_dinh_dang(self):
        """MIME/duoi client khai KHONG duoc tin — Pillow giai ma ra JPEG
        thi van xu ly nhu JPEG, khong tu choi vi 'duoi sai'."""
        ket = normalize_avatar(_jpeg())
        self.assertEqual(ket.mime, "image/webp")

    def test_jpeg_kem_exif_orientation_duoc_xoay_va_xoa_metadata(self):
        tho = _jpeg_with_exif_orientation(size=(300, 200), orientation=6)
        ket = normalize_avatar(tho)
        # Khong con crash o `n_frames` (JpegImageFile khong co thuoc tinh
        # nay), va khong con EXIF nao trong dau ra.
        lai = Image.open(io.BytesIO(ket.data))
        self.assertNotIn("exif", lai.info)
        self.assertIsNone(lai.getexif().get(0x0112))

    def test_cmyk_jpeg_duoc_chuyen_ve_rgb_thanh_cong(self):
        buf = io.BytesIO()
        Image.new("CMYK", (120, 80)).save(buf, format="JPEG")
        ket = normalize_avatar(buf.getvalue())
        self.assertEqual(ket.mime, "image/webp")
        lai = Image.open(io.BytesIO(ket.data))
        self.assertIn(lai.mode, ("RGB", "RGBA"))

    def test_palette_png_co_trong_suot_thanh_cong(self):
        img = Image.new("P", (100, 60))
        img.putpalette([i for i in range(256) for _ in range(3)])
        buf = io.BytesIO()
        img.save(buf, format="PNG", transparency=0)
        ket = normalize_avatar(buf.getvalue())
        self.assertEqual(ket.mime, "image/webp")

    def test_gif_dong_bi_tu_choi(self):
        with self.assertRaises(ImageValidationError):
            normalize_avatar(_animated_gif())

    def test_du_lieu_rac_bi_tu_choi(self):
        with self.assertRaises(ImageValidationError):
            normalize_avatar(b"khong phai anh gi ca " * 10)

    def test_tep_rong_bi_tu_choi(self):
        with self.assertRaises(ImageValidationError):
            normalize_avatar(b"")

    def test_svg_gia_dang_anh_bi_tu_choi(self):
        """SVG la XML — Pillow khong giai ma duoc, nen bi tu choi o buoc
        `Image.open()`/`verify()`, KHONG phai vi kiem duoi tep."""
        gia = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
        with self.assertRaises(ImageValidationError):
            normalize_avatar(gia)

    def test_vuot_qua_kich_thuoc_tep_dau_vao_bi_tu_choi(self):
        qua_kho = _png(size=(2000, 2000))
        # Ep tinh huong "vuot tran byte" ma khong can dung anh that qua lon:
        # kiem tran o day chi can do dai chuoi, dung mot khoi rac them vao.
        rac = qua_kho + b"0" * (AVATAR_MAX_INPUT_BYTES + 1 - len(qua_kho))
        self.assertGreater(len(rac), AVATAR_MAX_INPUT_BYTES)
        with self.assertRaises(ImageValidationError):
            normalize_avatar(rac)

    def test_canh_vuot_tran_bi_tu_choi(self):
        with self.assertRaises(ImageValidationError):
            normalize_avatar(_png(size=(MAX_INPUT_EDGE_PX + 100, 10)))

    def test_bomb_giai_nen_bi_tu_choi(self):
        """Anh kich thuoc HOP LE tung canh (duoi `MAX_INPUT_EDGE_PX`) nhung
        TICH so diem anh vuot `MAX_DECODED_PIXELS` — phep kiem TICH moi bat
        duoc truong hop nay, khong phai phep kiem canh."""
        w = MAX_INPUT_EDGE_PX  # 8000, khong vuot tran canh
        h = (MAX_DECODED_PIXELS // w) + 10  # tich vuot 40MP, canh h con nho
        self.assertLessEqual(max(w, h), MAX_INPUT_EDGE_PX)
        self.assertGreater(w * h, MAX_DECODED_PIXELS)
        with self.assertRaises(ImageValidationError):
            normalize_avatar(_png(size=(w, h)))


class ChuanHoaBannerTest(unittest.TestCase):
    def test_anh_rong_hon_ti_le_bi_cat_hai_ben(self):
        ket = normalize_banner(_png(size=(3000, 200)))
        self.assertEqual((ket.width, ket.height), (1500, 500))

    def test_anh_cao_hon_ti_le_bi_cat_tren_duoi(self):
        ket = normalize_banner(_png(size=(300, 3000)))
        self.assertEqual((ket.width, ket.height), (1500, 500))


class GioiHanOutTest(unittest.TestCase):
    def test_hinh_dang_co_du_khoa(self):
        ra = limits_out()
        for khoa in ("avatar_max_input_bytes", "banner_max_input_bytes",
                    "max_input_edge_px", "max_decoded_megapixels",
                    "avatar_output_size", "banner_output_size",
                    "accepted_mime"):
            self.assertIn(khoa, ra)


if __name__ == "__main__":
    unittest.main()
