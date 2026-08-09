"""
Pham vi giong cua WEB: chi tieng Viet, va muc "Giọng đề xuất" dung danh
sach do app desktop khai bao.

Quyet dinh san pham: ban web hien tai chi phuc vu giong tieng Viet. Registry
VAN giu du 452 giong moi thu tieng — desktop app dung chung registry do, va xoa
giong nuoc ngoai khoi registry la pha ho. Cai bi thu hep la PHAM VI CONG BO cua
web, bang cau hinh, nen mo lai ngon ngu khac sau nay chi la doi mot bien.

Danh sach de xuat KHONG duoc go tay o day. Nguon duy nhat la
`desktop_app/providers/recommended.py` — chinh danh sach chu du an da chon trong
app desktop. Moi test o duoi doi chieu voi nguon do chu khong voi mot ban chep.

Chay hoan toan offline: khong goi TTS, khong tao audio.
"""

from __future__ import annotations

import inspect
import unittest

from server import main as server_main
from server import tts_bridge
from server.config import Settings, _public_voice_languages
from desktop_app.providers.recommended import (
    RECOMMENDED_CODES,
    RECOMMENDED_COUNT,
    RECOMMENDED_FANFIC_VOICES,
)


class CauHinhGia:
    def __init__(self, *voices: str, languages=("vi",)):
        self.local_voices = tuple(voices) or ("piper:ngochuyen",)
        self.public_voice_languages = tuple(languages)


class GiongGia:
    def __init__(self, voice_id: str, language: str):
        self.id = voice_id
        self.language = language


class PhamViNgonNgu(unittest.TestCase):

    def test_mac_dinh_chi_tieng_viet(self) -> None:
        self.assertEqual(Settings.public_voice_languages, ("vi",))

    def test_khop_theo_tien_to_nen_vi_bat_duoc_vi_VN(self) -> None:
        s = CauHinhGia()
        self.assertTrue(tts_bridge.language_in_scope("vi-VN", s))
        self.assertTrue(tts_bridge.language_in_scope("vi", s))

    def test_ngon_ngu_khac_bi_loai(self) -> None:
        s = CauHinhGia()
        for ma in ("en-US", "ja-JP", "zh-CN", "es-ES", "ar-EG", ""):
            self.assertFalse(tts_bridge.language_in_scope(ma, s),
                             f"'{ma}' không được nằm trong phạm vi")

    def test_danh_sach_rong_nghia_la_khong_gioi_han(self) -> None:
        # Khac han `FAS_LOCAL_VOICES` (rong = tat het). Hai bien, hai y nghia
        # nguoc nhau, va do la co y — xem ghi chu o `server/config.py`.
        s = CauHinhGia(languages=())
        self.assertTrue(tts_bridge.language_in_scope("en-US", s))

    def test_doc_duoc_tu_bien_moi_truong(self) -> None:
        import os

        cu = os.environ.get("FAS_PUBLIC_VOICE_LANGUAGES")
        try:
            os.environ["FAS_PUBLIC_VOICE_LANGUAGES"] = "vi, en"
            self.assertEqual(_public_voice_languages(), ("vi", "en"))
            os.environ.pop("FAS_PUBLIC_VOICE_LANGUAGES")
            self.assertEqual(_public_voice_languages(),
                             Settings.public_voice_languages)
        finally:
            if cu is None:
                os.environ.pop("FAS_PUBLIC_VOICE_LANGUAGES", None)
            else:
                os.environ["FAS_PUBLIC_VOICE_LANGUAGES"] = cu

    def test_registry_VAN_giu_giong_nuoc_ngoai(self) -> None:
        """Thu hep pham vi web KHONG duoc xoa gi khoi registry."""
        vs = list(tts_bridge.get_registry().voices)
        ngoai = [v for v in vs
                 if not (v.language or "").lower().startswith("vi")]
        self.assertTrue(ngoai,
                        "registry phải còn giọng nước ngoài cho desktop app")


class ApiChiTraGiongTiengViet(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.vs = tts_bridge.list_voices(CauHinhGia())

    def test_khong_co_giong_nao_khac_tieng_viet(self) -> None:
        khac = [v["voice_id"] for v in self.vs
                if not v["language"].lower().startswith("vi")]
        self.assertEqual(khac, [])

    def test_van_con_du_giong_de_dung(self) -> None:
        self.assertGreater(len(self.vs), 7)

    def test_co_ca_capcut_lan_piper_duoc_duyet(self) -> None:
        nguon = {v["provider"] for v in self.vs}
        self.assertIn("capcut", nguon)
        self.assertIn("piper", nguon)

    def test_chi_giong_piper_duoc_duyet_moi_xuat_hien(self) -> None:
        piper = {v["voice_id"] for v in self.vs if v["provider"] == "piper"}
        self.assertEqual(piper, {"piper:ngochuyen"})


class MucGiongDeXuat(unittest.TestCase):
    """
    Dung cau hinh dang PRODUCTION, khong dung mac dinh cua `CauHinhGia`.

    Mac dinh o day chi bat `piper:ngochuyen`. Muc de xuat nay co HAI giong
    NghiTTS, va giong nao khong nam trong danh sach trang thi `list_voices()`
    loc di truoc — bo test se do trong khi ma nguon dung. Production bat ca 25
    giong NghiTTS, nen day moi la dieu kien can kiem.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.vs = tts_bridge.list_voices(
            CauHinhGia(*sorted(tts_bridge.nghitts_voice_ids())))
        cls.dx = sorted((v for v in cls.vs if v["recommended"]),
                        key=lambda v: v["recommended_order"])

    def test_dung_tam_giong(self) -> None:
        # Bay -> tam: them `piper:ngochuyennew` vao muc de xuat.
        self.assertEqual(RECOMMENDED_COUNT, 8)
        self.assertEqual(len(self.dx), 8)

    def test_dung_thu_tu_cua_app_desktop(self) -> None:
        """Doi chieu bang (provider, engine_voice_id) — ma ON DINH, khong phai ten."""
        from desktop_app.providers.recommended import voice_code

        reg = tts_bridge.get_registry()
        thuc_te = [voice_code(reg.voice_by_id(v["voice_id"])) for v in self.dx]
        self.assertEqual(thuc_te, list(RECOMMENDED_CODES))

    def test_thu_tu_lien_tuc_tu_khong(self) -> None:
        self.assertEqual([v["recommended_order"] for v in self.dx],
                         list(range(RECOMMENDED_COUNT)))

    def test_ca_hai_giong_NghiTTS_nam_trong_muc_de_xuat(self) -> None:
        # Lien nhau va dung cuoi: "Ngọc Huyền" roi "Ngọc Huyền (Mới)".
        ids = [v["voice_id"] for v in self.dx]
        self.assertEqual(ids[-2:],
                         ["piper:ngochuyen", "piper:ngochuyennew"])

    def test_khong_go_tay_danh_sach_o_backend(self) -> None:
        # Chep danh sach sang backend la cach chac chan de hai ban lech nhau.
        nguon = inspect.getsource(tts_bridge.list_voices)
        self.assertIn("RECOMMENDED_CODES", nguon)
        for _, ma, _ in RECOMMENDED_FANFIC_VOICES:
            self.assertNotIn(f'"{ma}"', nguon,
                             f"mã '{ma}' bị gõ tay vào tts_bridge")

    def test_de_xuat_va_danh_sach_day_du_dung_chung_ban_ghi(self) -> None:
        """Hai muc chi la hai cach trinh bay — khong nhan ban voice nao."""
        tat_ca = {v["voice_id"]: v for v in self.vs}
        for v in self.dx:
            self.assertIs(v, tat_ca[v["voice_id"]],
                          "giọng đề xuất phải là chính bản ghi trong danh sách đầy đủ")
        # Khong co id nao xuat hien hai lan trong ket qua tra ve.
        ids = [v["voice_id"] for v in self.vs]
        self.assertEqual(len(ids), len(set(ids)))


class TuChoiGiongNgoaiPhamVi(unittest.TestCase):

    def _mot_giong_nuoc_ngoai(self) -> str:
        for v in tts_bridge.get_registry().voices:
            if not (v.language or "").lower().startswith("vi"):
                return v.id
        self.skipTest("registry không có giọng nước ngoài nào")

    def test_goi_thang_id_nuoc_ngoai_bi_tu_choi(self) -> None:
        vid = self._mot_giong_nuoc_ngoai()
        with self.assertRaises(tts_bridge.TtsBridgeError) as ctx:
            tts_bridge.ensure_voice_public(vid, CauHinhGia())
        self.assertIn("tiếng Việt", ctx.exception.message)

    def test_khong_tu_chuyen_sang_giong_viet_khac(self) -> None:
        # `ensure_voice_public` chi duoc NEM loi. Khong duoc tra ve giong thay the.
        nguon = inspect.getsource(tts_bridge.ensure_voice_public)
        self.assertNotIn("return ", nguon,
                         "hàm này chỉ được ném lỗi, không được trả giọng thay thế")

    def test_id_khong_ton_tai_bi_tu_choi(self) -> None:
        with self.assertRaises(tts_bridge.TtsBridgeError):
            tts_bridge.ensure_voice_public("edge:khong-ton-tai-dau", CauHinhGia())

    def test_giong_viet_hop_le_di_qua(self) -> None:
        tts_bridge.ensure_voice_public("edge:vi-VN-HoaiMyNeural", CauHinhGia())
        tts_bridge.ensure_voice_public("piper:ngochuyen", CauHinhGia())

    def test_route_tao_job_tra_400_chu_khong_500(self) -> None:
        nguon = inspect.getsource(server_main.create_job)
        vi_tri = nguon.index("ensure_voice_public")
        self.assertIn("HTTP_400_BAD_REQUEST", nguon[vi_tri:vi_tri + 400])


class DuLieuCuKhongBiPha(unittest.TestCase):
    """Thu hep pham vi khong duoc lam hong chuong/audio da co."""

    def test_worker_KHONG_ap_gioi_han_ngon_ngu(self) -> None:
        """
        Job cu dang `pending` voi giong nuoc ngoai van phai chay xong.

        Neu worker cung ap gioi han ngon ngu thi doi cau hinh se lam hong nhung
        job da nam trong hang doi — thu hep pham vi la quyet dinh ve viec CHAO
        BAN cai gi tu hom nay, khong phai lenh huy nhung gi da nhan.
        """
        nguon = inspect.getsource(tts_bridge.ensure_voice_runnable)
        self.assertNotIn("language_in_scope", nguon)

    def test_duong_phat_audio_khong_dung_toi_voice_id(self) -> None:
        # Chuong cu tao bang giong nuoc ngoai van phai phat duoc.
        for ten in ("audio_url", "audio"):
            ham = getattr(server_main, ten, None)
            if ham is None:
                continue
            self.assertNotIn("ensure_voice", inspect.getsource(ham))

    def test_khong_co_duong_nao_sua_voice_id_cua_du_lieu_cu(self) -> None:
        nguon = inspect.getsource(server_main)
        self.assertNotIn("job.voice_id =", nguon)
        self.assertNotIn("track.voice_id =", nguon)


class DinhTuyenDungProvider(unittest.TestCase):

    def test_ngochuyen_di_ve_piper(self) -> None:
        v = tts_bridge.resolve_voice("piper:ngochuyen")
        self.assertEqual(v.provider, "piper")
        self.assertEqual(v.engine_voice_id, "ngochuyen")

    def test_cac_giong_capcut_de_xuat_di_ve_capcut(self) -> None:
        reg = tts_bridge.get_registry()
        capcut = [(p, ma) for p, ma, _ in RECOMMENDED_FANFIC_VOICES
                  if p == "capcut"]
        self.assertEqual(len(capcut), 5)
        for _, ma in capcut:
            khop = [v for v in reg.voices
                    if v.provider == "capcut" and v.engine_voice_id == ma]
            self.assertTrue(khop, f"không tìm thấy giọng CapCut '{ma}'")
            self.assertTrue(khop[0].language.lower().startswith("vi"))

    def test_hoai_my_di_ve_edge(self) -> None:
        v = tts_bridge.resolve_voice("edge:vi-VN-HoaiMyNeural")
        self.assertEqual(v.provider, "edge")


if __name__ == "__main__":
    unittest.main()
