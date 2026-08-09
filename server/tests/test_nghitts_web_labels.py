"""
Nhan hien thi cua giong NghiTTS tren WEB.

Bo test nay ton tai vi mot loi CU THE da len toi production: `/api/voices` bao
ra giong NghiTTS kem `provider_label="Piper local"`, `status="not_installed"`,
`status_label="Chưa tải model"` va `status_reason="... hãy chọn file .onnx và
.onnx.json trong Cài đặt."` — nen giao dien hien nguyen van

    "Ngọc Huyền (mới) · Piper local · máy riêng · Chưa tải model"

Ba manh, ba loai sai khac nhau:

  * "Piper local" — dung cho app desktop, o do model that su nam tren may
    nguoi dung. Nguoi dung web khong cai gi ca.
  * "Chưa tải model" — den tu `registry.status_of()`, ham soi he thong tep cua
    CHINH TIEN TRINH NAY. Tien trinh API tren Render khong co tep `.onnx` nao,
    con model thi nam tren may chu tong hop GCE. Cau tra loi dung voi mot cau
    hoi khac han.
  * "máy riêng" — dung khi worker con chay tren laptop chu du an. Production
    chay 24/7 tren GCE.

Ca ba deu bao nguoi dung rang giong ho vua chon KHONG dung duoc, trong khi no
dung duoc. Do la ly do phai khoa lai.
"""

from __future__ import annotations

import unittest

from desktop_app.providers.recommended import RECOMMENDED_CODES
from server import tts_bridge


class CauHinhGia:
    """Bat DUNG bo giong NghiTTS ma production dang bat."""

    def __init__(self, *ids: str):
        self.local_voices = tuple(ids) if ids else tuple(
            sorted(tts_bridge.nghitts_voice_ids()))
        self.public_voice_languages = ("vi",)


class NhanCuaGiongNghiTTS(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.vs = tts_bridge.list_voices(CauHinhGia())
        cls.piper = [v for v in cls.vs if v["provider"] == "piper"]

    def test_ca_bo_NghiTTS_deu_ra(self) -> None:
        self.assertEqual(len(self.piper), len(tts_bridge.nghitts_voice_ids()))

    def test_provider_label_la_NghiTTS(self) -> None:
        for v in self.piper:
            self.assertEqual(v["provider_label"], "NghiTTS", v["voice_id"])

    def test_khong_con_chu_Piper_local(self) -> None:
        """Chuoi nay tung hien nguyen van tren giao dien production."""
        for v in self.piper:
            for truong in ("provider_label", "status_label", "status_reason"):
                self.assertNotIn("Piper local", v[truong] or "", v["voice_id"])

    def test_khong_con_bao_chua_tai_model(self) -> None:
        for v in self.piper:
            self.assertNotEqual(v["status"], "not_installed", v["voice_id"])
            self.assertNotIn("Chưa tải model", v["status_label"] or "")

    def test_khong_bao_nguoi_dung_web_di_chon_file_onnx(self) -> None:
        """Nguoi dung web khong co Cai dat, khong co dia, khong co tep nao."""
        for v in self.piper:
            ly_do = v["status_reason"] or ""
            for cam in (".onnx", "Cài đặt", "tải model"):
                self.assertNotIn(cam, ly_do, v["voice_id"])

    def test_trang_thai_noi_dung_su_that_ma_API_biet(self) -> None:
        for v in self.piper:
            self.assertEqual(v["status"], tts_bridge.WORKER_STATUS)
            self.assertEqual(v["status_label"],
                             tts_bridge.WORKER_STATUS_LABEL)

    def test_khong_hua_san_sang(self) -> None:
        """
        Tien trinh API KHONG biet dia cua worker. No biet giong duoc duyet va
        noi tong hop la may chu — het. Hua "sẵn sàng" la doan, va doan sai thi
        nguoi dung cho mai mot job khong ai chay duoc.
        """
        for v in self.piper:
            self.assertNotIn("Sẵn sàng", v["status_label"] or "")
            self.assertNotEqual(v["status"], "available")

    def test_voice_id_van_la_khoa_ben_vung(self) -> None:
        """
        Doi nhan hien thi KHONG duoc dong toi `voice_id`: khoa do da nam trong
        job va track da tao, va o `content_hash` sinh ra `output_key` tren R2.
        """
        ids = {v["voice_id"] for v in self.piper}
        self.assertEqual(ids, set(tts_bridge.nghitts_voice_ids()))
        for i in ids:
            self.assertTrue(i.startswith("piper:"), i)

    def test_khong_goi_status_of_cho_giong_worker(self) -> None:
        """
        Chan lai o muc MA NGUON, khong chi o ket qua: goi lai `status_of()` cho
        giong cuc bo la du de trang thai he thong tep cua Render ro ri tro lai
        vao API, va no se ro ri duoi mot ten truong khac.
        """
        import inspect

        nguon = inspect.getsource(tts_bridge.list_voices)
        vi_tri = nguon.index("status_of")
        truoc = nguon[:vi_tri]
        self.assertIn("if is_local:", truoc,
                      "`status_of()` phải nằm trong nhánh KHÔNG-cục-bộ")


class KhongDungToiCapCutVaEdge(unittest.TestCase):
    """Yeu cau ro rang: khong xoa va khong doi giong nao khac."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.vs = tts_bridge.list_voices(CauHinhGia())

    def test_van_con_du_giong_capcut_va_edge(self) -> None:
        from desktop_app.providers.builtin_catalog import EDGE_BUILTIN

        capcut = [v for v in self.vs if v["provider"] == "capcut"]
        edge = [v for v in self.vs if v["provider"] == "edge"]
        self.assertGreater(len(capcut), 0)
        self.assertEqual(len(edge), len(EDGE_BUILTIN))

    def test_nhan_cua_capcut_va_edge_khong_bi_doi(self) -> None:
        """Chung chay qua mang, khong qua worker — nhan cu van dung."""
        khac = [v for v in self.vs if v["provider"] != "piper"]
        for v in khac:
            self.assertNotEqual(v["provider_label"], "NghiTTS", v["voice_id"])
            self.assertFalse(v["runs_on_worker"], v["voice_id"])


class GiongDeXuatPhaiThucSuDuocPhucVu(unittest.TestCase):
    """
    Mot giong NghiTTS duoc chon lam "đề xuất" nhung KHONG nam trong danh sach
    trang se bien mat khoi giao dien ma khong bao gi — `list_voices` loc no di
    truoc khi muc de xuat duoc dung. Muc de xuat ngan di mot dong, va khong co
    log nao noi vi sao.
    """

    def test_moi_ma_de_xuat_piper_deu_co_that_trong_catalog(self) -> None:
        vu_tru = tts_bridge.nghitts_voice_ids()
        for provider, khoa in RECOMMENDED_CODES:
            if provider != tts_bridge.LOCAL_PROVIDER:
                continue
            self.assertIn(f"{provider}:{khoa}", vu_tru,
                          f"'{provider}:{khoa}' được đề xuất nhưng không có "
                          "trong catalog NghiTTS — sẽ không bao giờ hiện ra")

    def test_cau_hinh_mac_dinh_tu_nhat_quan(self) -> None:
        """
        Mac dinh cua `Settings` phai tu du: moi giong NghiTTS duoc de xuat deu
        phai nam trong `local_voices` mac dinh. Neu khong, mot ban trien khai
        khong dat `FAS_LOCAL_VOICES` se co muc de xuat thieu giong.
        """
        from server.config import Settings

        cho_phep = tts_bridge.allowed_local_voice_ids(Settings())
        for provider, khoa in RECOMMENDED_CODES:
            if provider != tts_bridge.LOCAL_PROVIDER:
                continue
            self.assertIn(f"{provider}:{khoa}", cho_phep)

    def test_de_xuat_hien_ra_khi_danh_sach_trang_du(self) -> None:
        de_xuat = [v for v in tts_bridge.list_voices(CauHinhGia())
                   if v["recommended"] and v["provider"] == "piper"]
        mong_doi = [f"{p}:{k}" for p, k in RECOMMENDED_CODES
                    if p == tts_bridge.LOCAL_PROVIDER]
        self.assertEqual(sorted(v["voice_id"] for v in de_xuat),
                         sorted(mong_doi))


if __name__ == "__main__":
    unittest.main()
