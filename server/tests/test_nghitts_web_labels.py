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
from pathlib import Path

from desktop_app.providers.builtin_catalog import NGHITTS_DISPLAY_NAMES
from desktop_app.providers.recommended import RECOMMENDED_CODES
from server import tts_bridge

#: Bang ten chinh thuc do chu du an cung cap, chep NGUYEN VAN vao bo test.
#:
#: Co y KHONG import tu `builtin_catalog` roi so voi chinh no — lam vay thi bo
#: test chi chung minh "ma nguon bang chinh no", va mot lan go nham dau sac se
#: di qua ma khong ai thay. Doi ten hien thi phai sua o HAI cho, va do la muc
#: dich.
TEN_CHINH_THUC = {
    "adam1": "Adam",
    "banmai": "Ban Mai",
    "calmwoman3688": "Nữ Điềm Đạm",
    "chieuthanh": "Chiêu Thanh",
    "deepman3909": "Nam Trầm",
    "duyoryx3175": "Duy Oryx",
    "lacphi": "Lạc Phi",
    "maiphuong": "Mai Phương",
    "manhdung": "Mạnh Dũng",
    "minhkhang": "Minh Khang",
    "minhquang": "Minh Quang",
    "minhthu": "Minh Thư",
    "mytam2": "Mỹ Tâm 1",
    "mytam2794": "Mỹ Tâm 2",
    "ngochuyen": "Ngọc Huyền",
    "ngochuyennew": "Ngọc Huyền (Mới)",
    "ngocngan3701": "Ngọc Ngân",
    "phuongtrang": "Phương Trang",
    "taian2": "Tài An 1",
    "taian4": "Tài An 2",
    "thanhphuong2": "Thanh Phương",
    "thientam": "Thiên Tâm",
    "tranthanh3870": "Trần Thanh",
    "vietthao3886": "Việt Thảo",
    "yannew": "Yan (Mới)",
}


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

    def test_display_name_dung_bang_ten_chinh_thuc(self) -> None:
        thuc_te = {v["voice_id"]: v["display_name"] for v in self.piper}
        mong_doi = {f"piper:{k}": t for k, t in TEN_CHINH_THUC.items()}
        self.assertEqual(thuc_te, mong_doi)

    def test_khong_con_ten_ky_thuat_lam_ten_hien_thi(self) -> None:
        """
        Truoc day 22 giong lay CHINH `voice_key` lam `display_name`, nen giao
        dien hien "adam1", "maiphuong". Nay da co bang ten that.
        """
        for v in self.piper:
            khoa = v["voice_id"].split(":", 1)[1]
            self.assertNotEqual(v["display_name"], khoa, v["voice_id"])

    def test_ten_hien_thi_khong_lap_lai_ten_bo_giong(self) -> None:
        for v in self.piper:
            for cam in ("NghiTTS", "Piper", "piper", "máy riêng"):
                self.assertNotIn(cam, v["display_name"], v["voice_id"])

    def test_ten_hien_thi_khong_trung_nhau(self) -> None:
        """Hai dong trung ten trong mot `<select>` la khong chon duoc dung."""
        ten = [v["display_name"] for v in self.piper]
        self.assertEqual(len(set(ten)), len(ten), "có tên hiển thị trùng nhau")

    def test_hoan_doi_hau_to_moi_dung_huong(self) -> None:
        """
        `ngochuyen` truoc day mang ten "Ngọc Huyền (mới)". Bang ten chinh thuc
        chuyen hau to do sang `ngochuyennew`. Day la mot HOAN DOI, khong phai
        doi ten mot chieu — khoa lai de khong ai vo tinh doi nguoc.
        """
        theo_id = {v["voice_id"]: v["display_name"] for v in self.piper}
        self.assertEqual(theo_id["piper:ngochuyen"], "Ngọc Huyền")
        self.assertEqual(theo_id["piper:ngochuyennew"], "Ngọc Huyền (Mới)")

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


class DoiTenKhongDuocDongToiKhoa(unittest.TestCase):
    """
    `voice_key` == ten tep `.onnx` tren may chu tong hop, va `voice_id` xay tu
    no. Doi ten hien thi ma lo tay vao day thi worker tim khong ra model va moi
    job hong `MODEL_NOT_INSTALLED` — mot cach hong ma bo test nhan chi doc ten
    hien thi se khong bat duoc.
    """

    KHOA_MONG_DOI = frozenset(TEN_CHINH_THUC)

    def test_bo_voice_key_khong_doi(self) -> None:
        from desktop_app.providers.builtin_catalog import PIPER_BUILTIN

        self.assertEqual({i["voice_key"] for i in PIPER_BUILTIN},
                         self.KHOA_MONG_DOI)

    def test_bang_ten_phu_dung_bo_khoa_do(self) -> None:
        self.assertEqual(set(NGHITTS_DISPLAY_NAMES), self.KHOA_MONG_DOI)

    def test_voice_id_xay_tu_voice_key_khong_qua_bang_tra_nao(self) -> None:
        self.assertEqual(
            {f"piper:{k}" for k in self.KHOA_MONG_DOI},
            set(tts_bridge.nghitts_voice_ids()))


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

    def test_tong_so_giong_dung_51(self) -> None:
        """24 CapCut + 2 Edge + 25 NghiTTS."""
        from collections import Counter

        dem = Counter(v["provider"] for v in self.vs)
        self.assertEqual(dict(dem), {"capcut": 24, "edge": 2, "piper": 25})
        self.assertEqual(len(self.vs), 51)

    def test_metadata_provider_van_giu_nguyen(self) -> None:
        """
        Bo nhan bo giong khoi TEN HIEN THI la viec cua giao dien. API van phai
        bao ra `provider`, `provider_label` va `runs_on_worker` — giao dien
        khac (hoac ban sau) con can chung de phan biet.
        """
        piper = [v for v in self.vs if v["provider"] == "piper"]
        for v in piper:
            self.assertEqual(v["provider_label"], "NghiTTS")
            self.assertTrue(v["runs_on_worker"])


class FixtureChoBoTestWeb(unittest.TestCase):
    """
    `web/tests/fixtures/voices-production.json` la ban chup `/api/voices` voi
    dung 25 giong production. Bo test web doc no de kiem nhan hien thi ma
    khong phai chay Python.

    Mot fixture chep tay se troi khoi may chu sau vai lan sua, va troi mot cach
    IM LANG: bo test web van xanh trong khi no dang kiem mot su that da cu.
    Bai test nay la day noi giua hai ben.
    """

    DUONG_DAN = (Path(__file__).resolve().parents[2]
                 / "web" / "tests" / "fixtures" / "voices-production.json")

    #: Truong DUY NHAT bi loai khoi phep so, va vi mot ly do cu the.
    #:
    #: `installed` tra loi "TIEN TRINH NAY co tep model khong" — no phu thuoc
    #: dia cua may dang chay. May cua nguoi phat trien co model `ngochuyen`
    #: nen no `True`; may CI khong co nen `False`. Dua no vao phep so thi
    #: fixture khong the dung dong thoi o ca hai noi, va bo test se do o dung
    #: mot ben — da xay ra that.
    #:
    #: Loai no ra la AN TOAN vi giao dien khong doc no cho giong NghiTTS:
    #: `usableVoices()` dung `installed || runs_on_worker`, va `runs_on_worker`
    #: moi la co dung cho giong chay tren may chu tong hop.
    BO_QUA = ("installed",)

    def _doc(self) -> list:
        import json

        return json.loads(self.DUONG_DAN.read_text(encoding="utf-8"))

    def test_fixture_khop_voi_may_chu(self) -> None:
        def chuan(ds):
            return sorted(
                [{k: v for k, v in m.items() if k not in self.BO_QUA}
                 for m in ds],
                key=lambda v: v["voice_id"])

        self.assertEqual(
            chuan(self._doc()), chuan(tts_bridge.list_voices(CauHinhGia())),
            "fixture đã trôi khỏi `list_voices()` — sinh lại nó, đừng sửa tay")

    def test_fixture_mo_phong_may_KHONG_co_model(self) -> None:
        """
        Fixture phai chup dung hinh dang cua tien trinh API tren Render: khong
        co tep `.onnx` nao. Sinh no tren may CO model se ghi `installed=True`
        cho giong do, va bo test web se vo tinh khang dinh mot dieu chi dung
        tren may cua mot nguoi.
        """
        piper = [v for v in self._doc() if v["provider"] == "piper"]
        self.assertEqual(len(piper), 25)
        for v in piper:
            self.assertFalse(v["installed"], v["voice_id"])

    def test_fixture_du_51_giong(self) -> None:
        self.assertEqual(len(self._doc()), 51)


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
