"""Chan lai su co THAT: job DRAFT bi NHAN roi chet vi giong khong duoc chao ban.

Su co (may AWS staging, 2026-09-04): `staging_draft_job_proof.py` dat cung
`voice_id="piper:ngochuyennew"`. Do tren may that:

    voice_runnable_on_this_machine('piper:ngochuyennew') = True    <- cong VAT LY
    voice_is_local_allowed('piper:ngochuyennew')         = False   <- cong SAN PHAM
    ensure_voice_runnable -> TtsBridgeError
        "Giọng 'piper:ngochuyennew' hiện không được cung cấp."

Model CO that tren dia (63.516.050 byte, symlink .onnx.json -> config.json
hop le, doc duoc), nen cong VAT LY cho qua va worker NHAN job — roi chet o
cong SAN PHAM. Job khong duoc nhuong cho ai, va phep chung minh bao FAIL vi
mot ly do khong lien quan gi den AWS.

HAI CONG DOC LAP, va do la co y (xem docstring cua chinh hai ham):
    voice_runnable_on_this_machine   "may nay co model khong"  -> NHAN/NHUONG
    voice_is_local_allowed           "co duoc chao ban khong"  -> chay/tu choi

Bo test nay chay tren CAY MODEL GIA co dung hinh dang cua ban da trien khai
(25 `.onnx` + MOT `config.json` + 25 symlink), nen no chay duoc o moi noi,
khong doi may co 1.5GB model that.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

GIONG_MAC_DINH = "piper:ngochuyen"
GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN = "piper:ngochuyennew"
GIONG_KHONG_CO_MODEL = "piper:khong-ton-tai-tren-may-nay"


def cay_model_gia(goc: Path, ten: list[str]) -> Path:
    """Dung lai DUNG hinh dang tren may that: N `.onnx` + MOT `config.json`
    dung chung + N symlink `<voice>.onnx.json -> config.json`."""
    d = goc / "piper-tts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text('{"sample_rate": 22050}', encoding="utf-8")
    for v in ten:
        (d / f"{v}.onnx").write_bytes(b"ONNX-GIA" + b"\0" * 64)
        lien = d / f"{v}.onnx.json"
        try:
            if lien.exists() or lien.is_symlink():
                lien.unlink()
            lien.symlink_to("config.json")
        except (OSError, NotImplementedError):
            # Windows khong co quyen tao symlink -> lui ve tep thuong. Hinh
            # dang khac mot chut nhung cau hoi dang kiem (phan giai duoc hay
            # khong) van tra loi duoc.
            lien.write_text('{"sample_rate": 22050}', encoding="utf-8")
    return d


class TestPhanGiaiGiong(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.models = cay_model_gia(Path(self.d.name),
                                    ["ngochuyen", "ngochuyennew", "banmai"])
        self._cu = dict(os.environ)
        os.environ["FAS_PIPER_MODELS_DIR"] = str(self.models)
        os.environ["FAS_ENV"] = "staging"
        os.environ["DATA_BACKEND"] = "mock"
        os.environ["STORAGE_BACKEND"] = "local"
        self.addCleanup(self._khoi_phuc)

    def _khoi_phuc(self):
        os.environ.clear()
        os.environ.update(self._cu)

    def _bridge(self):
        from server import tts_bridge
        return tts_bridge

    def _settings(self, local_voices):
        """Settings toi thieu — chi can `local_voices` cho cong SAN PHAM."""
        class S:
            pass
        s = S()
        s.local_voices = tuple(local_voices)
        s.allow_unverified_local_voices = False
        return s

    # -- cay model da trien khai phan giai duoc -----------------------------
    def test_model_va_config_phan_giai_duoc(self):
        for v in ("ngochuyen", "ngochuyennew"):
            onnx = self.models / f"{v}.onnx"
            cfg = self.models / f"{v}.onnx.json"
            self.assertTrue(onnx.is_file(), f"{v}.onnx phai co")
            self.assertTrue(cfg.is_file(),
                            f"{v}.onnx.json phai PHAN GIAI duoc (symlink khong gay)")
            self.assertTrue(os.access(onnx, os.R_OK), f"{v}.onnx phai doc duoc")
            self.assertTrue(os.access(cfg, os.R_OK), f"{v}.onnx.json phai doc duoc")

    def test_khong_co_symlink_gay(self):
        gay = [p.name for p in self.models.iterdir()
               if p.is_symlink() and not p.exists()]
        self.assertEqual(gay, [], f"symlink gay: {gay}")

    # -- CONG VAT LY --------------------------------------------------------
    #
    # Cong nay di qua `get_registry()` (co cache), nen kiem no bang mot cay
    # model gia tren dia la khong tat dinh: registry co the da duoc dung tu
    # truoc trong cung tien trinh. Thay vao do TIEM registry — kiem dung HOP
    # DONG cua ham, khong kiem cache cua registry.
    def _voi_registry(self, ten_giong, installed):
        from unittest import mock
        from server import tts_bridge as b

        class Giong:
            pass
        g = Giong()
        g.installed = installed

        class Reg:
            def voice_by_id(self, vid):
                return g if vid == ten_giong else None
        return mock.patch.object(b, "get_registry", lambda: Reg())

    def test_cong_vat_ly_CHO_QUA_khi_model_DA_CAI(self):
        b = self._bridge()
        v = GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN
        with self._voi_registry(v, installed=True):
            self.assertTrue(b.voice_runnable_on_this_machine(v),
                            "da cai -> worker NHAN job")

    def test_cong_vat_ly_TU_CHOI_khi_model_CHUA_CAI(self):
        """Chua cai -> NHUONG (bo_qua_thieu_model), KHONG giet job.

        Day la nua con lai cua bat bien: worker khong duoc nhan mot job no
        khong chay duoc roi danh dau `failed`, vi lam vay la giet vinh vien
        mot job ma may khac lam duoc.
        """
        b = self._bridge()
        v = GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN
        with self._voi_registry(v, installed=False):
            self.assertFalse(b.voice_runnable_on_this_machine(v),
                             "chua cai -> phai NHUONG cho may khac")

    def test_giong_LA_KHONG_BIET_van_cho_qua(self):
        """Hop dong da ghi trong docstring: giong khong co trong registry tra
        True, de duong cu xu ly (nhan -> that bai co thong diep) thay vi de
        job treo `pending` vo han. De day de khoi ai 'sua' nham."""
        b = self._bridge()
        self.assertTrue(b.voice_runnable_on_this_machine(GIONG_KHONG_CO_MODEL))

    def test_giong_KHONG_cuc_bo_luon_chay_duoc(self):
        b = self._bridge()
        for v in ("capcut:ngochuyen", "edge:vi-VN-HoaiMyNeural"):
            self.assertTrue(b.voice_runnable_on_this_machine(v),
                            "giong khong cuc bo khong can model")

    # -- CONG SAN PHAM ------------------------------------------------------
    def test_cong_san_pham_tu_choi_giong_ngoai_danh_sach(self):
        """DAY LA SU CO: co model nhung khong duoc chao ban."""
        b = self._bridge()
        s = self._settings([GIONG_MAC_DINH])
        self.assertFalse(
            b.voice_is_local_allowed(GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN, s))
        with self.assertRaises(Exception) as ngoai:
            b.ensure_voice_runnable(GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN, s)
        self.assertIn("không được cung cấp", str(ngoai.exception))

    def test_danh_sach_RONG_tu_choi_MOI_giong(self):
        """`FAS_LOCAL_VOICES=` (rong) -> local_voices=() -> tu choi tat ca."""
        b = self._bridge()
        s = self._settings([])
        for v in (GIONG_MAC_DINH, GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN):
            self.assertFalse(b.voice_is_local_allowed(v, s),
                             f"{v} phai bi tu choi khi danh sach rong")

    def test_giong_MAC_DINH_qua_CA_HAI_cong(self):
        """Dieu kien de phep chung minh DRAFT chay duoc: mot giong phai qua
        CA HAI cong. Day chinh la thu ma su co da thieu."""
        b = self._bridge()
        s = self._settings([GIONG_MAC_DINH])
        with self._voi_registry(GIONG_MAC_DINH, installed=True):
            self.assertTrue(b.voice_runnable_on_this_machine(GIONG_MAC_DINH),
                            "cong VAT LY")
        self.assertTrue(b.voice_is_local_allowed(GIONG_MAC_DINH, s),
                        "cong SAN PHAM")
        b.ensure_voice_runnable(GIONG_MAC_DINH, s)   # khong duoc nem

    def test_tai_hien_DUNG_su_co_qua_cong_1_truot_cong_2(self):
        """Tai hien chinh xac hinh dang da lam job chet tren AWS."""
        b = self._bridge()
        s = self._settings([GIONG_MAC_DINH])          # chi chao ban ngochuyen
        v = GIONG_CO_MODEL_NHUNG_KHONG_CHAO_BAN       # ngochuyennew
        with self._voi_registry(v, installed=True):
            qua_cong_1 = b.voice_runnable_on_this_machine(v)
        qua_cong_2 = b.voice_is_local_allowed(v, s)
        self.assertTrue(qua_cong_1, "co model -> worker NHAN job")
        self.assertFalse(qua_cong_2, "nhung khong duoc chao ban")
        # => job bi NHAN roi CHET, khong duoc nhuong. Dung cai da xay ra.
        with self.assertRaises(Exception):
            b.ensure_voice_runnable(v, s)

    # -- phep chon giong cua ban chung minh ---------------------------------
    def test_proof_KHONG_dong_cung_ten_giong(self):
        """`staging_draft_job_proof.py` phai CHON theo ca hai cong.

        Dong cung mot ten chinh la nguyen nhan su co: `ngochuyennew` qua cong
        vat ly nhung truot cong san pham.
        """
        src = (GOC / "scripts" / "ops" /
               "staging_draft_job_proof.py").read_text(encoding="utf-8")
        self.assertIn("voice_is_local_allowed", src,
                      "phai kiem CA cong san pham, khong chi cong vat ly")
        self.assertIn("voice_runnable_on_this_machine", src)
        xau = [f"dong {i}" for i, l in enumerate(src.splitlines(), 1)
               if l.strip().startswith("GIONG =")
               and "ngochuyennew" in l]
        self.assertEqual(xau, [], "khong duoc dong cung `ngochuyennew` lam mac dinh")


if __name__ == "__main__":
    unittest.main()
