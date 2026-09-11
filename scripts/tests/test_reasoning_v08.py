"""Bài kiểm V0.8 — Strategist + Reviewer + bộ định tuyến model động.

TẤT ĐỊNH, KHÔNG MẠNG, KHÔNG TIẾN TRÌNH MODEL NÀO. Cả tệp chạy với fabric
dựng tay và `BoGoiGia` — cùng lý do `test_router_v4_scheduler.py` không đọc
`config/fabric.json`: một thay đổi cấu hình thật không được âm thầm làm bài
kiểm nói dối, và ngược lại.

Mỗi lớp khoá lại MỘT tính chất mà nếu mất đi thì v0.8 mất nghĩa. Thứ tự các
lớp theo đúng thứ tự mục §21 của yêu cầu.
"""
from __future__ import annotations

import unittest
from typing import Dict, List, Optional

from scripts.control_center.reasoning import chinh_sach as CS
from scripts.control_center.reasoning import hop_dong as HD
from scripts.control_center.reasoning import ngan_sach as NS
from scripts.control_center.reasoning import ngu_canh as NC
from scripts.control_center.reasoning.dinh_tuyen import (BoDinhTuyenVai,
                                                         KhongCoCho,
                                                         ly_do_leo_thang,
                                                         trong_so_cho)
from scripts.control_center.reasoning.goi import BoGoiGia, LuotVai
from scripts.control_center.reasoning.hoi_dong import HoiDong
from scripts.control_center.reasoning.phan_loai import (Bac, PhamVi, TacDong,
                                                        lap_ke_hoach_vai,
                                                        phan_loai_luot)
from scripts.control_center.reasoning.that_bai import (ChinhSachThuLai,
                                                       HanhDong, LoaiThatBai,
                                                       phan_loai_that_bai)
from scripts.control_center.reasoning.vai import VaiTro, ho_so
from scripts.router_v4.capabilities import Reasoning
from scripts.router_v4.premium import MODEL_ASTRA, CheDo, GacAstra
from scripts.router_v4.runtime import (Fabric, ModelCapability, QuotaPool,
                                       RuntimeStatus, Source, WorkerRuntime)
from scripts.router_v4.scheduler import Scheduler

# --------------------------------------------------------------- tinh huong --
#
# Sáu câu A–F lấy NGUYÊN VĂN từ mục §15 của yêu cầu v0.8, cộng ba câu ví dụ
# của §3. Chúng là bộ hiệu chuẩn của bộ phân loại — sửa trọng số mà làm hỏng
# một dòng ở đây là đã đổi hành vi sản phẩm, không phải tinh chỉnh nội bộ.

A = "production farmer hiện chạy không?"
B = "vụ SSH key trước đây là gì?"
C = "tại sao mấy hôm nay Drive không có production mới?"
D = ("theo trạng thái hiện tại, project Fanfic nên ưu tiên phát triển phần "
     "nào tiếp theo và tại sao?")
E = ("hãy đề xuất một redesign lớn cho production architecture và phản biện "
     "chính đề xuất đó.")
F = "ê bro"
G_COMMIT = "commit gần nhất là gì?"
G_SCALE = "kiến trúc Fanfic nên thay đổi thế nào để scale?"
G_MIGRATE = "có nên migrate Appwrite/storage architecture không?"
THUC_THI = "sửa giúp bug ở scripts/control_center/store.py rồi chạy test"


def _model(mid, *, family, caps=("structured_output", "long_context"),
           pool="p", reasoning=Reasoning.HIGH, bench=0.8, provider="antigravity",
           latency=30.0, cost=0.5, tier=0,
           source=Source.PROBED) -> ModelCapability:
    return ModelCapability(
        model_id=mid, model_family=family, provider=provider,
        capabilities=frozenset(caps),
        capability_source={c: source for c in caps},
        quota_pool=pool, reasoning=reasoning, benchmark_profile=bench,
        latency_profile=latency, cost_profile=cost, premium_tier=tier,
        provider_model=mid)


def _rt(rid, *, models, account=None, provider="antigravity", conc=3,
        needs="") -> WorkerRuntime:
    return WorkerRuntime(
        runtime_id=rid, provider=provider, account_id=account or f"acct-{rid}",
        auth_profile=f"profile:{rid}", supported_models=tuple(models),
        concurrency=conc, status=RuntimeStatus.IDLE, needs_provisioning=needs)


def fabric_thu(*, co_astra: bool = False, chi_mot_ho: bool = False) -> Fabric:
    """Fabric nhỏ đủ để phân biệt họ model, bậc giá và bậc cao cấp."""
    f = Fabric()
    f.add_model(_model("gem-flash", family="gemini", bench=0.8, latency=25.0,
                       cost=0.3))
    if not chi_mot_ho:
        f.add_model(_model("claude-opus", family="claude", bench=0.9,
                           latency=90.0, cost=0.9, source=Source.DECLARED))
        f.add_model(_model("gpt-oss", family="gpt", bench=0.55, latency=30.0,
                           cost=0.5, reasoning=Reasoning.MEDIUM))
    mo = ["gem-flash"] + ([] if chi_mot_ho else ["claude-opus", "gpt-oss"])
    if co_astra:
        f.add_model(_model(MODEL_ASTRA, family="codex", provider="codex",
                           pool="px", bench=0.9, latency=90.0, cost=1.0,
                           tier=3, source=Source.DECLARED))
        f.add_runtime(_rt("CODEX01", models=[MODEL_ASTRA], provider="codex",
                          conc=1))
        f.add_pool(QuotaPool(pool_id="acct-CODEX01:px",
                             account_id="acct-CODEX01",
                             member_models=frozenset({MODEL_ASTRA}),
                             source=Source.DECLARED))
    f.add_runtime(_rt("AG01", models=mo))
    f.add_pool(QuotaPool(pool_id="acct-AG01:p", account_id="acct-AG01",
                         member_models=frozenset(mo), source=Source.DECLARED))
    f.validate()
    return f


class KyUcGia:
    """`DichVuKyUc` giả — chỉ hai phương thức mà `chinh_sach.py` dùng."""

    def __init__(self, quyet_dinh: Optional[Dict[str, List[Dict]]] = None):
        self._qd = quyet_dinh or {}

    def liet_ke(self, project_id, loai, *, limit=100):
        return {"san_sang": True,
                "ket_qua": list((self._qd.get(project_id) or {}).get(loai, []))}

    def tim(self, project_id, cau, *, loai="", limit=30):
        return {"san_sang": True, "ket_qua": []}


def _qd(ma, noi_dung, *, ts=1_700_000_000.0, trang_thai="hieu_luc"):
    return {"ma": ma, "trang_thai": trang_thai, "ts": ts,
            "ky_uc": {"ma": f"ku_{ma}", "noi_dung": noi_dung, "ts": ts}}


# ===========================================================================
# 1. Phân loại độ khó / tác động
# ===========================================================================

class Test01PhanLoai(unittest.TestCase):
    """Sáu tình huống nghiệm thu phải rơi đúng lớp. Đây là hợp đồng hành vi
    của v0.8 với người dùng, không phải một chi tiết nội bộ."""

    def test_A_tra_cuu_song_la_tam_thuong(self):
        p = phan_loai_luot(A)
        self.assertTrue(p.la_tam_thuong)
        self.assertIs(p.tac_dong, TacDong.THAP)
        self.assertFalse(p.la_thuc_thi,
                         "‘chạy không?’ là câu hỏi TRẠNG THÁI, không phải lệnh")

    def test_B_lich_su_la_tam_thuong(self):
        self.assertTrue(phan_loai_luot(B).la_tam_thuong)

    def test_C_chan_doan_KHONG_bi_coi_la_lich_su(self):
        """"tại sao …" là dấu hiệu lịch sử, nhưng câu này hỏi về HIỆN TẠI."""
        p = phan_loai_luot(C)
        self.assertFalse(p.la_tam_thuong)
        self.assertTrue(p.dac_trung.la_chan_doan)
        self.assertFalse(p.dac_trung.la_lich_su)
        self.assertIs(p.bac, Bac.THUONG)

    def test_D_cau_hoi_chien_luoc_la_KHO(self):
        p = phan_loai_luot(D)
        self.assertIs(p.bac, Bac.KHO)
        self.assertTrue(p.dac_trung.chien_luoc_du_an)
        self.assertFalse(p.dac_trung.la_lich_su,
                         "‘và tại sao’ không biến câu chiến lược thành câu "
                         "lịch sử")

    def test_E_kien_truc_production_la_RAT_KHO_tac_dong_CAO(self):
        p = phan_loai_luot(E)
        self.assertIs(p.bac, Bac.RAT_KHO)
        self.assertIs(p.tac_dong, TacDong.CAO)
        self.assertIs(p.pham_vi, PhamVi.MULTI_SYSTEM)
        self.assertTrue(p.dac_trung.doi_phan_bien)
        self.assertFalse(p.dao_nguoc_duoc)

    def test_F_xa_giao(self):
        p = phan_loai_luot(F)
        self.assertTrue(p.la_tam_thuong)
        self.assertTrue(p.dac_trung.la_xa_giao)

    def test_xa_giao_chi_khi_NGAN(self):
        """"ê bro" là tán gẫu; "ê bro, <câu hỏi kiến trúc>" thì không."""
        p = phan_loai_luot("ê bro, kiến trúc storage nên đổi thế nào để scale?")
        self.assertFalse(p.dac_trung.la_xa_giao)
        self.assertFalse(p.la_tam_thuong)

    def test_tra_cuu_kho(self):
        self.assertTrue(phan_loai_luot(G_COMMIT).la_tam_thuong)

    def test_migrate_kien_truc_la_RAT_KHO_CAO(self):
        p = phan_loai_luot(G_MIGRATE)
        self.assertIs(p.bac, Bac.RAT_KHO)
        self.assertIs(p.tac_dong, TacDong.CAO)

    def test_chu_production_KHONG_bien_cau_kien_truc_thanh_tra_cuu(self):
        """Khuyết tật hiệu chuẩn đo được: `la_cau_hoi_van_hanh` bắt chữ
        "production", nên câu E từng bị cổng tầm thường nuốt."""
        self.assertFalse(phan_loai_luot(E).dac_trung.la_tra_cuu_song)

    def test_giai_thich_neu_dau_hieu(self):
        van = phan_loai_luot(E).giai_thich()
        self.assertIn("độ khó", van)
        self.assertIn("dấu hiệu đã bắt", van)

    def test_tat_dinh(self):
        self.assertEqual(phan_loai_luot(E).to_dict(),
                         phan_loai_luot(E).to_dict())


# ===========================================================================
# 2. Chọn vai + chế độ chất lượng
# ===========================================================================

class Test02ChonVai(unittest.TestCase):

    def _vai(self, cau, cd):
        return {v.value for v in lap_ke_hoach_vai(phan_loai_luot(cau), cd).vai}

    def test_cong_tam_thuong_thang_MOI_che_do(self):
        """Rào CỨNG: MAX cũng không được gọi vai cho một câu chào/tra cứu."""
        for cau in (A, B, F, G_COMMIT):
            for cd in CheDo:
                with self.subTest(cau=cau[:20], che_do=cd.value):
                    self.assertEqual(self._vai(cau, cd), {"leader"})

    def test_D_AUTO_co_strategist_khong_reviewer(self):
        self.assertEqual(self._vai(D, CheDo.AUTO), {"leader", "strategist"})

    def test_E_moi_che_do_co_ca_hai(self):
        for cd in CheDo:
            with self.subTest(che_do=cd.value):
                self.assertEqual(self._vai(E, cd),
                                 {"leader", "strategist", "reviewer"})

    def test_ECO_khong_tu_them_reviewer(self):
        """ECO = 'minimal escalation': Reviewer chỉ chạy khi NGƯỜI DÙNG xin."""
        self.assertEqual(self._vai(G_SCALE, CheDo.ECO),
                         {"leader", "strategist"})
        self.assertEqual(self._vai(G_SCALE, CheDo.AUTO),
                         {"leader", "strategist", "reviewer"})

    def test_ECO_leo_thang_it_hon_AUTO(self):
        self.assertEqual(self._vai(D, CheDo.ECO), {"leader"})

    def test_STRONG_leo_thang_som_hon_AUTO(self):
        self.assertEqual(self._vai(C, CheDo.AUTO), {"leader"})
        self.assertIn("strategist", self._vai(C, CheDo.STRONG))

    def test_yeu_cau_thuc_thi_de_KHONG_goi_hoi_dong(self):
        kh = lap_ke_hoach_vai(phan_loai_luot(THUC_THI), CheDo.MAX)
        self.assertEqual({v.value for v in kh.vai}, {"leader"})
        self.assertIn("THỰC THI", kh.ly_do)

    def test_do_tin_thap_chan_leo_thang_o_AUTO(self):
        p = phan_loai_luot(D)
        p.do_tin = 0.1
        self.assertEqual({v.value for v in lap_ke_hoach_vai(p, CheDo.AUTO).vai},
                         {"leader"})
        # STRONG la lua chon TUONG MINH cua nguoi dung -> khong doi do tin.
        self.assertIn("strategist",
                      {v.value for v in lap_ke_hoach_vai(p, CheDo.STRONG).vai})

    def test_ly_do_KHONG_khoe_mot_nguong_chua_dat(self):
        """ECO + câu bậc THUONG có chữ "phản biện": Strategist chạy vì NGƯỜI
        DÙNG XIN, không phải vì đủ bậc — lý do phải nói đúng điều đó."""
        p = phan_loai_luot("phản biện giúp tôi cái này")
        kh = lap_ke_hoach_vai(p, CheDo.ECO)
        if "strategist" in {v.value for v in kh.vai} and p.bac is not Bac.RAT_KHO:
            self.assertNotIn("≥ RAT_KHO", kh.ly_do)
            self.assertIn("người dùng xin phản biện", kh.ly_do)

    def test_ke_hoach_ghi_nguong_da_dung(self):
        kh = lap_ke_hoach_vai(phan_loai_luot(D), CheDo.AUTO)
        self.assertEqual(kh.nguong["bac_toi_thieu"], "KHO")
        self.assertIn("do_tin_toi_thieu", kh.nguong)


# ===========================================================================
# 3. Chính sách dự án (tra từ KÝ ỨC, không chép vào mã)
# ===========================================================================

class Test03ChinhSach(unittest.TestCase):

    ASTRA = ("GPT-6 Astra chỉ được dùng cho các task đặc biệt khó hoặc cần "
             "reasoning cao, không dùng mặc định cho task thường.")

    def test_doc_tu_ky_uc_va_neu_ma(self):
        kc = KyUcGia({"fanfic": {"decision": [_qd("qd_0001", self.ASTRA)]}})
        cs = CS.doc_chinh_sach(kc, "fanfic", ten_model=(MODEL_ASTRA,))
        self.assertTrue(cs.han_che)
        self.assertEqual(cs.nguon, "ky_uc")
        self.assertEqual(cs.ma, "qd_0001")
        self.assertTrue(cs.co_bang_chung)
        self.assertIn("qd_0001", cs.ly_do())

    def test_khong_co_ky_uc_thi_HAN_CHE(self):
        cs = CS.doc_chinh_sach(KyUcGia(), "trong", ten_model=(MODEL_ASTRA,))
        self.assertTrue(cs.han_che)
        self.assertEqual(cs.nguon, "khong_co_ky_uc")
        self.assertFalse(cs.co_bang_chung)

    def test_ky_uc_hong_thi_FAIL_CLOSED(self):
        class Vo:
            def liet_ke(self, *a, **k):
                raise RuntimeError("sổ hỏng")

            def tim(self, *a, **k):
                return {}
        cs = CS.doc_chinh_sach(Vo(), "x", ten_model=(MODEL_ASTRA,))
        self.assertTrue(cs.han_che)
        self.assertEqual(cs.nguon, "fail_closed")

    def test_dich_vu_None_thi_HAN_CHE(self):
        self.assertTrue(CS.doc_chinh_sach(None, "x").han_che)

    def test_quyet_dinh_NOI_LONG_duoc_ton_trong(self):
        """Chính sách là của DỰ ÁN. Một quyết định nới lỏng phải thắng —
        nếu không thì đây là hằng số chép cứng đội lốt một phép tra."""
        kc = KyUcGia({"p": {"decision": [
            _qd("qd_9", "gpt-6-astra được dùng tự do cho mọi task")]}})
        self.assertFalse(CS.doc_chinh_sach(kc, "p",
                                           ten_model=(MODEL_ASTRA,)).han_che)

    def test_mau_thuan_thi_giu_HAN_CHE(self):
        kc = KyUcGia({"p": {"decision": [
            _qd("qd_9", "gpt-6-astra chỉ được dùng cho việc khó, "
                        "nhưng cũng dùng mặc định cho mọi task")]}})
        self.assertTrue(CS.doc_chinh_sach(kc, "p",
                                          ten_model=(MODEL_ASTRA,)).han_che)

    def test_moi_nhat_thang(self):
        kc = KyUcGia({"p": {"decision": [
            _qd("qd_1", "gpt-6-astra chỉ được dùng cho việc đặc biệt khó",
                ts=1000.0),
            _qd("qd_2", "gpt-6-astra được dùng tự do cho mọi task", ts=2000.0),
        ]}})
        cs = CS.doc_chinh_sach(kc, "p", ten_model=(MODEL_ASTRA,))
        self.assertEqual(cs.ma, "qd_2")
        self.assertFalse(cs.han_che)

    def test_quyet_dinh_bi_thay_the_bi_bo(self):
        kc = KyUcGia({"p": {"decision": [
            _qd("qd_1", "gpt-6-astra được dùng tự do cho mọi task",
                trang_thai="bi_thay_the")]}})
        self.assertEqual(CS.doc_chinh_sach(kc, "p",
                                           ten_model=(MODEL_ASTRA,)).nguon,
                         "khong_co_ky_uc")

    def test_CO_LAP_DU_AN(self):
        """Quyết định của dự án A KHÔNG được rò sang dự án B."""
        kc = KyUcGia({"a": {"decision": [
            _qd("qd_1", "gpt-6-astra được dùng tự do cho mọi task")]}})
        self.assertFalse(CS.doc_chinh_sach(kc, "a",
                                           ten_model=(MODEL_ASTRA,)).han_che)
        cs_b = CS.doc_chinh_sach(kc, "b", ten_model=(MODEL_ASTRA,))
        self.assertTrue(cs_b.han_che)
        self.assertEqual(cs_b.nguon, "khong_co_ky_uc")

    def test_ten_model_cao_cap_doc_theo_BAC(self):
        ten = CS.ten_model_cao_cap(fabric_thu(co_astra=True))
        self.assertIn(MODEL_ASTRA, ten)


# ===========================================================================
# 4. Astra: chặn mặc định, leo thang có lý do
# ===========================================================================

class Test04Astra(unittest.TestCase):

    def setUp(self):
        self.f = fabric_thu(co_astra=True)
        self.cs_han = CS.ChinhSachCaoCap(han_che=True, nguon="ky_uc",
                                         ma="qd_0001",
                                         trich="chỉ dùng cho việc đặc biệt khó")
        # CODEX01 phai KHAI Astra trong `supported_models` de bai kiem nay do
        # dung thu no muon do: RAO CHINH SACH, chu khong phai "khong co cho".
        self.f.runtimes["CODEX01"].supported_models = (MODEL_ASTRA,)

    def _bdt(self, cs=None):
        return BoDinhTuyenVai(self.f, chinh_sach=cs or self.cs_han)

    def test_khong_bao_gio_cho_luot_THUONG(self):
        p = phan_loai_luot(C)
        cv = self._bdt().chon(VaiTro.STRATEGIST, p, CheDo.STRONG)
        self.assertFalse(cv.astra)
        self.assertNotEqual(cv.model_id, MODEL_ASTRA)

    def test_ECO_cam_tuyet_doi(self):
        cv = self._bdt().chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.ECO,
                              nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv.astra)
        self.assertIn("ECO", cv.astra_ly_do)

    def test_chua_tra_chinh_sach_thi_FAIL_CLOSED(self):
        cv = BoDinhTuyenVai(self.f, chinh_sach=None).chon(
            VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
            nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv.astra)
        self.assertIn("FAIL CLOSED", cv.astra_ly_do)

    def test_leo_thang_duoc_khi_du_bon_dieu_kien(self):
        cv = self._bdt().chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                              nguoi_yeu_cau_cao_cap=True)
        self.assertTrue(cv.astra, cv.astra_ly_do)
        self.assertEqual(cv.model_id, MODEL_ASTRA)
        self.assertIn("nguoi_yeu_cau", cv.astra_ly_do)

    def test_ghi_lai_VI_SAO_ca_khi_KHONG_leo_thang(self):
        cv = self._bdt().chon(VaiTro.STRATEGIST, phan_loai_luot(D), CheDo.AUTO)
        self.assertFalse(cv.astra)
        self.assertTrue(cv.astra_ly_do.strip(),
                        "một lần KHÔNG leo thang cũng phải giải thích được")

    def test_ly_do_leo_thang_None_cho_viec_khong_RAT_KHO(self):
        self.assertIsNone(ly_do_leo_thang(phan_loai_luot(C)))
        self.assertIsNotNone(ly_do_leo_thang(phan_loai_luot(E)))

    def test_khong_co_placement_thi_ha_ve_bac_thuong_KHONG_de_quy(self):
        """Ghim một model không runtime nào chạy được từng gây `RecursionError`
        sau ~990 tầng — đo thật trên fabric thật."""
        self.f.runtimes["CODEX01"].supported_models = ()
        cv = self._bdt().chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                              nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv.astra)
        self.assertTrue(cv.co_cho)
        self.assertIn("hạ về bậc thường", cv.astra_ly_do)

    def test_chinh_sach_THEO_LUOT_thang_chinh_sach_cua_bo_dinh_tuyen(self):
        """`BoDinhTuyenVai` dùng CHUNG cho mọi dự án trong một tiến trình.

        Gắn chính sách vào `self` sẽ áp quyết định của dự án A cho lượt của
        dự án B — đúng thứ `chinh_sach.py` tồn tại để chặn. Bản đầu đọc chính
        sách ra rồi KHÔNG truyền xuống, nên `qd_0001` chỉ là trang trí và mọi
        lượt đều rơi vào nhánh `fail_closed`.
        """
        bdt = BoDinhTuyenVai(self.f, chinh_sach=None)
        cv0 = bdt.chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                       nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv0.astra)
        self.assertIn("FAIL CLOSED", cv0.astra_ly_do)

        cv1 = bdt.chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                       nguoi_yeu_cau_cao_cap=True, chinh_sach=self.cs_han)
        self.assertTrue(cv1.astra, cv1.astra_ly_do)
        self.assertIn("qd_0001", cv1.astra_ly_do)

        # Va no KHONG dinh lai vao bo dinh tuyen cho luot sau.
        cv2 = bdt.chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                       nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv2.astra, "chính sách lượt trước bị rò sang lượt sau")

    def test_hoi_dong_TRUYEN_chinh_sach_xuong_bo_dinh_tuyen(self):
        from scripts.control_center.reasoning.goi import BoGoiGia, LuotVai
        from scripts.control_center.reasoning.hoi_dong import HoiDong

        gia = BoGoiGia(kich_ban={VaiTro.STRATEGIST: [
            LuotVai(ok=True, van_ban='{"de_xuat":"x"}')]})
        hd = HoiDong(bo_dinh_tuyen=BoDinhTuyenVai(self.f, chinh_sach=None),
                     bo_goi=gia)
        kq = hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.MAX,
                     khoi_san_co={}, chinh_sach=self.cs_han)
        ng = kq.nguon_goc[0]
        self.assertIn("qd_0001", ng.chon.astra_ly_do,
                      "chính sách dự án phải tới được tầng định tuyến, "
                      "không chỉ được ghi vào báo cáo")

    def test_gac_astra_van_la_rao_doc_lap(self):
        gac = GacAstra(tran_song_song=0)
        bdt = BoDinhTuyenVai(self.f, chinh_sach=self.cs_han, gac=gac)
        cv = bdt.chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.MAX,
                      nguoi_yeu_cau_cao_cap=True)
        self.assertFalse(cv.astra)


# ===========================================================================
# 5. Khớp năng lực + vai không có công cụ
# ===========================================================================

class Test05NangLuc(unittest.TestCase):

    def setUp(self):
        self.bdt = BoDinhTuyenVai(fabric_thu())

    def test_vai_suy_luan_KHONG_doi_cong_cu(self):
        """`agy --print` tự chối mọi công cụ cần duyệt quyền (đo 2026-09-10).
        Một vai đòi `repo_read` sẽ được xếp lên chỗ không đọc nổi tệp."""
        for vai in (VaiTro.LEADER, VaiTro.STRATEGIST, VaiTro.REVIEWER):
            yc = self.bdt.yeu_cau_cho_vai(vai, phan_loai_luot(E), CheDo.AUTO)
            with self.subTest(vai=vai.value):
                self.assertFalse(yc.repo_read)
                self.assertFalse(yc.repo_write)
                self.assertFalse(yc.shell)
                self.assertTrue(yc.structured_output)

    def test_model_thieu_structured_output_bi_LOAI(self):
        f = Fabric()
        f.add_model(_model("khong-json", family="gemini", pool="",
                           caps=("long_context",)))
        f.add_runtime(_rt("AG01", models=["khong-json"]))
        f.validate()
        with self.assertRaises(KhongCoCho):
            BoDinhTuyenVai(f).chon(VaiTro.STRATEGIST, phan_loai_luot(E),
                                   CheDo.AUTO)

    def test_viec_RAT_KHO_nang_bac_suy_luan(self):
        yc = self.bdt.yeu_cau_cho_vai(VaiTro.STRATEGIST, phan_loai_luot(E),
                                      CheDo.AUTO)
        self.assertIs(yc.reasoning_level, Reasoning.HIGH)

    def test_ECO_ha_bac_suy_luan_khi_khong_RAT_KHO(self):
        yc = self.bdt.yeu_cau_cho_vai(VaiTro.LEADER, phan_loai_luot(D),
                                      CheDo.ECO)
        self.assertIs(yc.reasoning_level, Reasoning.MEDIUM)

    def test_ho_so_EXECUTOR_nem(self):
        with self.assertRaises(KeyError):
            ho_so(VaiTro.EXECUTOR)

    def test_nang_luc_bay_co_cau_truc(self):
        ds = self.bdt.nang_luc_bay()
        self.assertTrue(ds)
        m = ds[0]
        for k in ("placement", "nang_luc", "reasoning", "bac_gia",
                  "quota_con_lai", "quota_nguon", "hop_vai", "reliability"):
            self.assertIn(k, m)


# ===========================================================================
# 6. Chi phí / hạn mức — ngữ nghĩa UNKNOWN
# ===========================================================================

class Test06NganSach(unittest.TestCase):

    def test_bac_gia_theo_nguong(self):
        self.assertIs(NS.bac_chi_phi(0.1), NS.BacChiPhi.RE)
        self.assertIs(NS.bac_chi_phi(0.4), NS.BacChiPhi.TRUNG)
        self.assertIs(NS.bac_chi_phi(0.7), NS.BacChiPhi.DAT)
        self.assertIs(NS.bac_chi_phi(0.95), NS.BacChiPhi.CAO_CAP)

    def test_bac_cao_cap_THANG_con_so(self):
        self.assertIs(NS.bac_chi_phi(0.0, premium_tier=3), NS.BacChiPhi.CAO_CAP)

    def test_rao_tuong_xung_chan_model_dat_cho_viec_thuong(self):
        ok, vi_sao = NS.kiem_tuong_xung(bac_kho=Bac.THUONG,
                                        bac_gia=NS.BacChiPhi.CAO_CAP,
                                        che_do=CheDo.AUTO, model_id="x")
        self.assertFalse(ok)
        self.assertIn("VƯỢT", vi_sao)

    def test_ECO_ha_tran_them_mot_bac(self):
        self.assertIs(NS.tran_chi_phi(Bac.RAT_KHO, CheDo.AUTO),
                      NS.BacChiPhi.CAO_CAP)
        self.assertIs(NS.tran_chi_phi(Bac.RAT_KHO, CheDo.ECO),
                      NS.BacChiPhi.DAT)

    def test_usage_khong_do_duoc_la_None_khong_phai_0(self):
        ms = NS.usage_khong_do_duoc("codex")
        self.assertEqual(len(ms), 1)
        self.assertIsNone(ms[0].value)
        self.assertEqual(ms[0].confidence.value, "UNAVAILABLE")

    def test_ban_ghi_them_thoi_gian_tuong_la_ACTUAL(self):
        bg = NS.BanGhiDinhTuyen(vai=VaiTro.STRATEGIST, provider="antigravity",
                                giay=12.5)
        self.assertTrue(bg.co_usage_that)
        self.assertEqual(bg.usage[0].label, "thời gian tường")

    def test_ban_ghi_khong_co_giay_thi_KHONG_co_usage_that(self):
        bg = NS.BanGhiDinhTuyen(vai=VaiTro.STRATEGIST, provider="codex")
        self.assertFalse(bg.co_usage_that)

    def test_tong_giay_la_None_khi_khong_do_duoc(self):
        so = NS.SoDinhTuyen()
        so.them(NS.BanGhiDinhTuyen(vai=VaiTro.STRATEGIST, provider="codex"))
        self.assertIsNone(so.tong_giay, "0.0 đọc thành ‘chạy tức thì’")

    # -- han muc DO DUOC ----------------------------------------------------

    USAGE_THAT = (
        "Gemini Models\tWeekly Limit Remaining\t40%\t2026-09-12T05:39:35Z\n"
        "Gemini Models\tFive Hour Limit Remaining\t91%\t2026-09-11T09:26:01Z\n"
        "Claude and GPT models\tWeekly Limit Remaining\t10%\t2026-09-14T19:58:56Z\n"
        "Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-09-11T11:38:43Z")

    def test_doc_han_muc_cua_so_NHO_NHAT_thang(self):
        hm = NS.doc_han_muc_agy(self.USAGE_THAT)
        self.assertAlmostEqual(hm["antigravity_gemini"].con_lai, 0.40)
        self.assertAlmostEqual(hm["antigravity_claude_gpt"].con_lai, 0.10)
        self.assertEqual(hm["antigravity_claude_gpt"].cua_so, "weekly")

    def test_van_ban_khong_khop_thi_rong_KHONG_doan(self):
        self.assertEqual(NS.doc_han_muc_agy("xin chào"), {})
        self.assertEqual(NS.doc_han_muc_agy(""), {})

    def test_ap_han_muc_CHI_cho_dung_mot_tai_khoan(self):
        f = fabric_thu()
        f.add_runtime(_rt("AG02", models=["gem-flash"], account="acct-AG02"))
        f.add_pool(QuotaPool(pool_id="acct-AG02:p", account_id="acct-AG02",
                             member_models=frozenset({"gem-flash"}),
                             source=Source.DECLARED))
        hm = NS.doc_han_muc_agy(self.USAGE_THAT)
        hm = {"p": list(hm.values())[0]}     # gan nhan lai cho be `p` cua fabric thu
        doi = NS.ap_han_muc(f, hm, account_id="acct-AG01")
        self.assertEqual(doi, ["acct-AG01:p"])
        self.assertIs(f.pools["acct-AG01:p"].source, Source.PROBED)
        self.assertIs(f.pools["acct-AG02:p"].source, Source.DECLARED)

    def test_ap_han_muc_khong_co_tai_khoan_thi_KHONG_ap(self):
        f = fabric_thu()
        self.assertEqual(NS.ap_han_muc(f, {"p": NS.HanMucDoDuoc("p", 0.1)},
                                       account_id=""), [])


# ===========================================================================
# 7. Độc lập của Reviewer
# ===========================================================================

class Test07DocLap(unittest.TestCase):

    def test_reviewer_khac_ho_voi_strategist(self):
        bdt = BoDinhTuyenVai(fabric_thu())
        p = phan_loai_luot(E)
        s = bdt.chon(VaiTro.STRATEGIST, p, CheDo.AUTO)
        r = bdt.chon(VaiTro.REVIEWER, p, CheDo.AUTO, ho_tac_gia=s.model_family,
                     doi_doc_lap=True)
        self.assertNotEqual(r.model_family, s.model_family)
        self.assertTrue(r.doc_lap)
        self.assertFalse(r.suy_giam)

    def test_mot_ho_duy_nhat_thi_bao_DEGRADED_chu_khong_gia_vo(self):
        bdt = BoDinhTuyenVai(fabric_thu(chi_mot_ho=True))
        p = phan_loai_luot(E)
        r = bdt.chon(VaiTro.REVIEWER, p, CheDo.AUTO, ho_tac_gia="gemini",
                     doi_doc_lap=True)
        self.assertTrue(r.co_cho)
        self.assertFalse(r.doc_lap)
        self.assertTrue(r.suy_giam)
        self.assertIn("KHÔNG", r.suy_giam_ly_do)

    def test_khong_doi_doc_lap_thi_doc_lap_la_None(self):
        bdt = BoDinhTuyenVai(fabric_thu())
        cv = bdt.chon(VaiTro.STRATEGIST, phan_loai_luot(E), CheDo.AUTO)
        self.assertIsNone(cv.doc_lap)


# ===========================================================================
# 8. Trọng số theo vai / chế độ
# ===========================================================================

class Test08TrongSo(unittest.TestCase):

    def test_strategist_uu_tien_chat_luong_hon_do_tre(self):
        goc = Scheduler(fabric_thu()).weights
        w = trong_so_cho(goc, VaiTro.STRATEGIST, CheDo.AUTO)
        self.assertGreater(w.benchmark_quality, goc.benchmark_quality)
        self.assertLess(w.latency, goc.latency)
        self.assertLess(w.expected_cost, goc.expected_cost)

    def test_leader_uu_tien_do_tre(self):
        goc = Scheduler(fabric_thu()).weights
        w = trong_so_cho(goc, VaiTro.LEADER, CheDo.AUTO)
        self.assertGreater(w.latency, goc.latency)

    def test_che_do_doi_trong_so_THAT(self):
        goc = Scheduler(fabric_thu()).weights
        eco = trong_so_cho(goc, VaiTro.STRATEGIST, CheDo.ECO)
        mx = trong_so_cho(goc, VaiTro.STRATEGIST, CheDo.MAX)
        self.assertGreater(eco.expected_cost, mx.expected_cost)
        self.assertGreater(mx.benchmark_quality, eco.benchmark_quality)

    def test_AUTO_giu_nguyen_trong_so_kho(self):
        goc = Scheduler(fabric_thu()).weights
        w = trong_so_cho(goc, VaiTro.STRATEGIST, CheDo.AUTO)
        self.assertEqual(w.availability, goc.availability)


# ===========================================================================
# 9. Hợp đồng chiến lược / phản biện
# ===========================================================================

class Test09HopDong(unittest.TestCase):

    JSON_CL = ('{"muc_tieu":"X","phuong_an":["A","B"],"danh_doi":["A đắt"],'
               '"de_xuat":"chọn A","rui_ro":["r1"],"viec_can_lam":["v1"],'
               '"do_tin":0.7,"cau_hoi_can_nguoi":["ai duyệt?"],'
               '"bang_chung":["qd_0001"]}')

    def test_doc_ban_chien_luoc(self):
        b = HD.doc_ban_chien_luoc(self.JSON_CL)
        self.assertEqual(b.de_xuat, "chọn A")
        self.assertEqual(b.do_tin, 0.7)
        self.assertTrue(b.dung_duoc)

    def test_json_boc_trong_rao(self):
        b = HD.doc_ban_chien_luoc("nè bạn:\n```json\n" + self.JSON_CL + "\n```")
        self.assertEqual(b.de_xuat, "chọn A")

    def test_chien_luoc_rong_thi_NEM(self):
        with self.assertRaises(HD.HopDongLoi):
            HD.doc_ban_chien_luoc('{"muc_tieu":"X"}')

    def test_doc_theo_tieu_de_van_xuoi(self):
        b = HD.doc_ban_chien_luoc(
            "Mục tiêu: scale\nPhương án:\n- A\n- B\nĐề xuất: chọn A vì rẻ\n"
            "Rủi ro:\n- mất dữ liệu")
        self.assertIn("chọn A", b.de_xuat)
        self.assertEqual(len(b.phuong_an), 2)

    def test_phan_xu_doc_duoc(self):
        for x in ("ACCEPT", "REVISE", "REJECT"):
            with self.subTest(x=x):
                self.assertIs(HD.doc_ban_phan_bien('{"phan_xu":"%s"}' % x).phan_xu,
                              HD.PhanXu(x))

    def test_phan_xu_KHONG_doc_duoc_thi_NEM(self):
        """FAIL CLOSED: đoán một REJECT thành ACCEPT là chế độ hỏng tệ nhất."""
        with self.assertRaises(HD.HopDongLoi):
            HD.doc_ban_phan_bien("bản này ổn đấy, mình thấy được")

    def test_accept_with_changes_thanh_REVISE(self):
        b = HD.doc_ban_phan_bien('{"phan_xu":"ACCEPT WITH CHANGES"}')
        self.assertIs(b.phan_xu, HD.PhanXu.REVISE)

    def test_do_tin_None_khac_0(self):
        self.assertIsNone(HD.doc_ban_phan_bien('{"phan_xu":"ACCEPT"}').do_tin)
        self.assertEqual(
            HD.doc_ban_phan_bien('{"phan_xu":"ACCEPT","do_tin":0}').do_tin, 0.0)

    def test_khoi_leader_KHONG_chua_nhac_nho_tho(self):
        b = HD.doc_ban_chien_luoc(self.JSON_CL)
        khoi = b.to_khoi_leader()
        self.assertNotIn("Bạn là **STRATEGIST**", khoi)
        self.assertIn("ĐỀ XUẤT", khoi)
        self.assertIn("CHƯA tạo việc nào", khoi)

    def test_khoi_reviewer_bao_SUY_GIAM(self):
        b = HD.doc_ban_phan_bien('{"phan_xu":"ACCEPT"}')
        self.assertIn("ĐỘ ĐỘC LẬP SUY GIẢM", b.to_khoi_leader(doc_lap=False))
        self.assertNotIn("SUY GIẢM", b.to_khoi_leader(doc_lap=True))


# ===========================================================================
# 10. Ngữ cảnh CÓ TRẦN + kê khai
# ===========================================================================

class Test10NguCanh(unittest.TestCase):

    def test_ke_khai_liet_ke_khoi_da_cap(self):
        g = NC.dung_goi(VaiTro.STRATEGIST,
                        khoi_san_co={"yeu_cau_nguoi_dung": "hỏi",
                                     "vien_nang": "nang", "ky_uc": "ky uc"})
        k = g.ke_khai()
        self.assertIn("vien_nang", k["ten_khoi_da_cap"])
        self.assertEqual(k["vai"], "strategist")
        self.assertGreater(k["tran_token"], 0)

    def test_cat_thi_NEU_TEN(self):
        """Khuyết tật V0.7: dòng cắt chỉ ĐẾM -> một lượt trả lời '5 account'
        trong khi sổ ghi 8."""
        g = NC.dung_goi(VaiTro.STRATEGIST,
                        khoi_san_co={"yeu_cau_nguoi_dung": "hỏi",
                                     "vien_nang": "x" * 400_000,
                                     "ky_uc": "y" * 400_000},
                        tran_token=200)
        self.assertTrue(g.da_cat)
        van = g.render()
        for t in g.da_cat:
            self.assertIn(NC.NHAN_KHOI[t], van)
        self.assertIn("KHÔNG phải giấy phép để đoán", van)

    def test_cau_nguoi_dung_KHONG_BAO_GIO_bi_cat(self):
        g = NC.dung_goi(VaiTro.STRATEGIST,
                        khoi_san_co={"yeu_cau_nguoi_dung": "câu thật",
                                     "vien_nang": "z" * 400_000},
                        tran_token=10)
        self.assertIn("yeu_cau_nguoi_dung", [k.ten for k in g.khoi])
        self.assertIn("câu thật", g.render())

    def test_ten_khoi_la_thi_vao_da_cat_khong_im_lang(self):
        g = NC.dung_goi(VaiTro.STRATEGIST,
                        khoi_san_co={"yeu_cau_nguoi_dung": "a", "gõ_sai": "b"})
        self.assertIn("gõ_sai", g.da_cat)

    def test_reviewer_uu_tien_ban_chien_luoc(self):
        g = NC.dung_goi(VaiTro.REVIEWER,
                        khoi_san_co={"yeu_cau_nguoi_dung": "a",
                                     "ban_chien_luoc": "BCL",
                                     "hoi_thoai": "h" * 100_000},
                        tran_token=300)
        ten = [k.ten for k in g.khoi]
        self.assertIn("ban_chien_luoc", ten)
        self.assertIn("hoi_thoai", g.da_cat)

    def test_ranh_gioi_tin_cay_luon_co(self):
        g = NC.dung_goi(VaiTro.STRATEGIST,
                        khoi_san_co={"yeu_cau_nguoi_dung": "a"})
        self.assertIn("KHÔNG PHẢI CHỈ THỊ", g.render())

    def test_tran_theo_vai(self):
        self.assertGreater(ho_so(VaiTro.STRATEGIST).tran_token_ngu_canh,
                           ho_so(VaiTro.LEADER).tran_token_ngu_canh)


# ===========================================================================
# 11. Phân loại thất bại + trần thử lại
# ===========================================================================

class Test11ThatBai(unittest.TestCase):

    def test_phan_loai(self):
        cases = [
            ({"loi": "rate limit exceeded"}, LoaiThatBai.QUOTA),
            ({"loi": "not logged in"}, LoaiThatBai.XAC_THUC),
            ({"loi": "codex_security_shaped_refusal"}, LoaiThatBai.NANG_LUC),
            ({"loi": "timeout sau 300s"}, LoaiThatBai.RUNTIME),
            ({"rong": True}, LoaiThatBai.RUNTIME),
            ({"doc_duoc": False, "van_ban": "bla"}, LoaiThatBai.VIEC),
        ]
        for kw, cho in cases:
            with self.subTest(kw=kw):
                self.assertIs(phan_loai_that_bai(**kw)[0], cho)

    def test_quota_duoc_kiem_TRUOC_runtime(self):
        loai, _ = phan_loai_that_bai(loi="error 429 rate limit")
        self.assertIs(loai, LoaiThatBai.QUOTA)

    def test_BAT_DONG_khong_bao_gio_dinh_tuyen_lai(self):
        """Đi tìm một model khác cho cùng câu hỏi là đi mua một ý kiến dễ chịu
        hơn — và lúc nào cũng còn một model nữa."""
        tl = ChinhSachThuLai()
        hd, vi_sao = tl.quyet_dinh(VaiTro.REVIEWER, LoaiThatBai.VIEC,
                                   placement="AG01/x")
        self.assertIs(hd, HanhDong.DUNG)
        self.assertIn("VẬN CHUYỂN", vi_sao)

    def test_xac_thuc_DUNG_can_nguoi(self):
        tl = ChinhSachThuLai()
        hd, _ = tl.quyet_dinh(VaiTro.STRATEGIST, LoaiThatBai.XAC_THUC)
        self.assertIs(hd, HanhDong.DUNG)

    def test_runtime_thu_lai_cung_cho_DUNG_MOT_LAN(self):
        tl = ChinhSachThuLai()
        tl.ghi_goi(VaiTro.STRATEGIST)
        self.assertIs(tl.quyet_dinh(VaiTro.STRATEGIST, LoaiThatBai.RUNTIME,
                                    placement="A/x")[0],
                      HanhDong.THU_LAI_CUNG_CHO)
        self.assertIs(tl.quyet_dinh(VaiTro.STRATEGIST, LoaiThatBai.RUNTIME,
                                    placement="A/x")[0],
                      HanhDong.DINH_TUYEN_LAI)

    def test_quota_dinh_tuyen_lai_va_LOAI_cho_hong(self):
        tl = ChinhSachThuLai()
        tl.ghi_goi(VaiTro.STRATEGIST)
        hd, _ = tl.quyet_dinh(VaiTro.STRATEGIST, LoaiThatBai.QUOTA,
                              placement="AG01/gem")
        self.assertIs(hd, HanhDong.DINH_TUYEN_LAI)
        self.assertIn("AG01/gem", tl.loai_tru(VaiTro.STRATEGIST))

    def test_tran_moi_vai(self):
        tl = ChinhSachThuLai(tran_moi_vai=2, tran_toan_luot=10)
        tl.ghi_goi(VaiTro.STRATEGIST)
        tl.ghi_goi(VaiTro.STRATEGIST)
        self.assertFalse(tl.con_cho_goi(VaiTro.STRATEGIST)[0])

    def test_tran_toan_luot_chan_ba_vai_cung_quay_vong(self):
        tl = ChinhSachThuLai(tran_moi_vai=5, tran_toan_luot=3)
        for _ in range(3):
            tl.ghi_goi(VaiTro.STRATEGIST)
        self.assertFalse(tl.con_cho_goi(VaiTro.REVIEWER)[0])


# ===========================================================================
# 12. Hội đồng — đầu-cuối, với BoGoiGia
# ===========================================================================

CL_OK = ('{"muc_tieu":"scale","phuong_an":["A","B"],"de_xuat":"chọn A",'
         '"rui_ro":["r"],"viec_can_lam":["v1","v2"],"do_tin":0.8}')
PB_OK = '{"phan_xu":"REVISE","bang_chung_thieu":["thiếu số liệu tải"]}'


class Test12HoiDong(unittest.TestCase):

    def _hd(self, kich_ban, *, f=None, cs=None):
        gia = BoGoiGia(kich_ban=kich_ban)
        bdt = BoDinhTuyenVai(f or fabric_thu(),
                             chinh_sach=cs or CS.ChinhSachCaoCap(
                                 han_che=True, nguon="ky_uc", ma="qd_0001"))
        return HoiDong(bo_dinh_tuyen=bdt, bo_goi=gia), gia

    def test_luot_tam_thuong_KHONG_goi_vai_nao(self):
        hd, gia = self._hd({})
        kq = hd.chay(cau=F, phan_loai=phan_loai_luot(F), che_do=CheDo.MAX,
                     khoi_san_co={})
        self.assertEqual(gia.da_goi, [])
        self.assertFalse(kq.da_chay)
        self.assertEqual(kq.khoi_leader(), "",
                         "lượt rẻ không được thêm một token nào cho Leader")

    def test_duong_day_du_strategist_va_reviewer(self):
        hd, gia = self._hd({VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK,
                                                        giay=3.0)],
                            VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB_OK,
                                                      giay=2.0)]})
        kq = hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.AUTO,
                     khoi_san_co={"vien_nang": "vn"}, project_id="p")
        self.assertTrue(kq.da_chay)
        self.assertEqual(kq.chien_luoc.de_xuat, "chọn A")
        self.assertIs(kq.phan_bien.phan_xu, HD.PhanXu.REVISE)
        self.assertEqual(len(gia.da_goi), 2)
        khoi = kq.khoi_leader()
        self.assertIn("REVISE", khoi)
        self.assertIn("KHÔNG TỰ TẠO VIỆC", khoi)

    def test_reviewer_nhan_BAN_CHIEN_LUOC(self):
        hd, gia = self._hd({VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK)],
                            VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB_OK)]})
        hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.AUTO,
                khoi_san_co={})
        nn = gia.nhac_nho_da_nhan[VaiTro.REVIEWER][0]
        self.assertIn("BẢN CHIẾN LƯỢC", nn)
        self.assertIn("chọn A", nn)

    def test_strategist_hong_thi_reviewer_BI_BO_QUA(self):
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=False, loi="not logged in")]})
        kq = hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.AUTO,
                     khoi_san_co={})
        self.assertIsNone(kq.chien_luoc)
        self.assertIsNone(kq.phan_bien)
        self.assertEqual([v for v, _r, _m in gia.da_goi], [VaiTro.STRATEGIST])
        self.assertTrue(kq.suy_giam)
        self.assertTrue(any("REVIEWER" in x for x in kq.loi))

    def test_dinh_tuyen_lai_khi_QUOTA(self):
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=False, loi="429 rate limit"),
            LuotVai(ok=True, van_ban=CL_OK)]})
        kq = hd.chay(cau=G_SCALE, phan_loai=phan_loai_luot(G_SCALE),
                     che_do=CheDo.ECO, khoi_san_co={})
        self.assertIsNotNone(kq.chien_luoc)
        self.assertEqual(len(gia.da_goi), 2)
        self.assertNotEqual(gia.da_goi[0][2], gia.da_goi[1][2],
                            "phải đổi model sau một lần hỏng QUOTA")

    def test_BAT_DONG_khong_sinh_luot_thu_hai(self):
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=True, van_ban="tôi không đồng ý và không trả JSON")]})
        kq = hd.chay(cau=G_SCALE, phan_loai=phan_loai_luot(G_SCALE),
                     che_do=CheDo.ECO, khoi_san_co={})
        self.assertIsNone(kq.chien_luoc)
        self.assertEqual(len(gia.da_goi), 1, "đầu ra không đọc được = VIEC, "
                                             "không định tuyến lại")

    def test_NANG_LUC_khong_hop_thi_dinh_tuyen_lai(self):
        """Codex từ chối việc "hình dạng bảo mật" (bằng chứng 2026-08-28).
        Đó là NĂNG LỰC không hợp — thử lại cùng chỗ là vô nghĩa."""
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=False, loi="codex_security_shaped_refusal"),
            LuotVai(ok=True, van_ban=CL_OK)]})
        kq = hd.chay(cau=G_SCALE, phan_loai=phan_loai_luot(G_SCALE),
                     che_do=CheDo.AUTO, khoi_san_co={})
        self.assertIsNotNone(kq.chien_luoc)
        # CHI dem luot cua STRATEGIST: G_SCALE o AUTO goi ca Reviewer, va
        # Reviewer khong co kich ban nen no cung sinh luot — dem gop lai se
        # do mot con so khong lien quan gi toi phep dinh tuyen lai dang kiem.
        st = [x for x in gia.da_goi if x[0] is VaiTro.STRATEGIST]
        self.assertEqual(len(st), 2)
        self.assertNotEqual(st[0][2], st[1][2],
                            "phải đổi placement sau khi năng lực không hợp")

    def test_XAC_THUC_bao_dung_va_KHONG_thu_cho_khac(self):
        """Mất xác thực cần NGƯỜI. Thử chỗ khác chỉ che mất việc đó."""
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=False, loi="not logged in"),
            LuotVai(ok=True, van_ban=CL_OK)]})
        kq = hd.chay(cau=G_SCALE, phan_loai=phan_loai_luot(G_SCALE),
                     che_do=CheDo.AUTO, khoi_san_co={})
        self.assertIsNone(kq.chien_luoc)
        self.assertEqual(len(gia.da_goi), 1, "KHÔNG được thử chỗ khác")
        ng = kq.nguon_goc[0]
        self.assertEqual(ng.loai_that_bai, "XAC_THUC")
        self.assertIn("đăng nhập", ng.ghi_chu)

    def test_thu_lai_CO_TRAN_khong_thanh_thac_nha_cung_cap(self):
        """Hỏng liên tục KHÔNG được biến thành một chuỗi vô tận."""
        hd, gia = self._hd({VaiTro.STRATEGIST: [
            LuotVai(ok=False, loi="429 rate limit") for _ in range(9)]})
        kq = hd.chay(cau=G_SCALE, phan_loai=phan_loai_luot(G_SCALE),
                     che_do=CheDo.AUTO, khoi_san_co={})
        self.assertIsNone(kq.chien_luoc)
        self.assertLessEqual(len(gia.da_goi), 2,
                             "trần mỗi vai là 2 lượt — không được vượt")

    def test_nguon_goc_ghi_du_de_giai_thich(self):
        hd, _ = self._hd({VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK,
                                                      giay=4.0)],
                          VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB_OK,
                                                    giay=1.0)]})
        kq = hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.AUTO,
                     khoi_san_co={"vien_nang": "vn"})
        d = kq.to_dict()
        self.assertEqual(len(d["nguon_goc"]), 2)
        for n in d["nguon_goc"]:
            self.assertIn("ngu_canh", n)
            self.assertIn("khoi_da_cap", n["ngu_canh"])
            self.assertTrue(n["ban_ghi"]["model_id"])
            self.assertTrue(n["ban_ghi"]["ly_do"])
        self.assertAlmostEqual(d["so"]["tong_giay"], 5.0)
        self.assertTrue(d["dong_nguon_goc"])

    def test_KHONG_tao_viec_trong_thao_luan(self):
        """§11: một đề xuất không phải một yêu cầu. `KetQuaHoiDong` không có
        đường nào tạo việc, và khối gửi Leader nói thẳng điều đó."""
        hd, _ = self._hd({VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK)],
                          VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB_OK)]})
        kq = hd.chay(cau=E, phan_loai=phan_loai_luot(E), che_do=CheDo.AUTO,
                     khoi_san_co={})
        self.assertFalse(hasattr(kq, "tasks"))
        self.assertFalse(kq.phan_loai.la_thuc_thi)
        khoi = kq.khoi_leader()
        self.assertIn("CHƯA tạo việc nào", khoi)
        self.assertIn("delegate_work", khoi)

    def test_yeu_cau_thuc_thi_van_la_thuc_thi(self):
        p = phan_loai_luot(THUC_THI)
        self.assertTrue(p.la_thuc_thi)
        hd, gia = self._hd({})
        kq = hd.chay(cau=THUC_THI, phan_loai=p, che_do=CheDo.MAX,
                     khoi_san_co={})
        self.assertEqual(gia.da_goi, [], "việc thực thi rõ ràng đi thẳng "
                                         "Router V4, không qua hội đồng")
        self.assertTrue(kq.phan_loai.la_thuc_thi)

    def test_su_kien_duoc_ghi(self):
        sk = []
        gia = BoGoiGia(kich_ban={
            VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK)]})
        bdt = BoDinhTuyenVai(fabric_thu())
        hd = HoiDong(bo_dinh_tuyen=bdt, bo_goi=gia,
                     ghi_su_kien=lambda k, **kw: sk.append(k))
        hd.chay(cau=D, phan_loai=phan_loai_luot(D), che_do=CheDo.AUTO,
                khoi_san_co={}, project_id="p")
        self.assertIn("REASONING_ROLE_OK", sk)
        self.assertIn("REASONING_COUNCIL", sk)

    def test_luot_bo_qua_cung_duoc_ghi(self):
        sk = []
        hd = HoiDong(bo_dinh_tuyen=BoDinhTuyenVai(fabric_thu()),
                     bo_goi=BoGoiGia(),
                     ghi_su_kien=lambda k, **kw: sk.append(k))
        hd.chay(cau=F, phan_loai=phan_loai_luot(F), che_do=CheDo.MAX,
                khoi_san_co={}, project_id="p")
        self.assertIn("REASONING_SKIPPED", sk,
                      "một lần KHÔNG leo thang cũng phải giải thích được")


# ===========================================================================
# 13. §18 — một đề xuất KHÔNG tự thành một quyết định trong ký ức
# ===========================================================================

class Test13KhongGhiKyUc(unittest.TestCase):
    """*"Do NOT store every Strategist brainstorm as an active Decision.
    User authority remains distinct from model recommendation."*

    Rào ở đây là CẤU TRÚC, không phải một lời dặn: cả gói `reasoning` không
    gọi một hàm ghi ký ức nào. Đường ghi DUY NHẤT vẫn là `record_memory` của
    Leader (tự chạy được, nhưng mang `tin_cay=leader` — thấp hơn tuyên bố
    tường minh của người dùng) và các endpoint người bấm.
    """

    GHI = ("ghi_ky_uc", "ghi_quyet_dinh", "cap_nhat_vien_nang",
           "de_bat", "diem_dung_tuong_minh", "luu_quyet_dinh")

    def test_goi_reasoning_KHONG_goi_ham_ghi_ky_uc_nao(self):
        import ast
        from pathlib import Path

        goc = Path(__file__).resolve().parents[2]
        thu_muc = goc / "scripts" / "control_center" / "reasoning"
        self.assertTrue(thu_muc.is_dir(), thu_muc)
        for tep in sorted(thu_muc.glob("*.py")):
            cay = ast.parse(tep.read_text(encoding="utf-8"))
            goi = set()
            for n in ast.walk(cay):
                if isinstance(n, ast.Call):
                    f = n.func
                    ten = (f.attr if isinstance(f, ast.Attribute)
                           else f.id if isinstance(f, ast.Name) else "")
                    if ten:
                        goi.add(ten)
            for x in self.GHI:
                with self.subTest(tep=tep.name, ham=x):
                    self.assertNotIn(
                        x, goi,
                        f"{tep.name} gọi {x}() — một đề xuất của model không "
                        f"được tự ghi vào ký ức dự án như một quyết định")

    def test_ket_qua_hoi_dong_KHONG_phoi_van_ban_tho(self):
        """§12: lộ metadata quyết định, KHÔNG lộ chuỗi suy nghĩ."""
        b = HD.doc_ban_chien_luoc('{"de_xuat":"x","phuong_an":["a"]}')
        self.assertTrue(b.tho, "vẫn giữ bản thô cho chẩn đoán…")
        self.assertNotIn("tho", b.to_dict(), "…nhưng KHÔNG đưa ra ngoài")
        p = HD.doc_ban_phan_bien('{"phan_xu":"ACCEPT"}')
        self.assertNotIn("tho", p.to_dict())


# ===========================================================================
# 14. Đường dây ENGINE — thứ mọi lớp trên đều mock đi mất
# ===========================================================================

class Test14DuongDayEngine(unittest.TestCase):
    """Nối `ControlCenter` thật với vai GIẢ.

    VÌ SAO CẦN, và nó không phải "thêm cho đủ": mọi lớp trên dựng
    `BoDinhTuyenVai`/`HoiDong` bằng tay, nên chúng KHÔNG chạy qua
    `engine.hoi_dong` — chỗ duy nhất nối fabric, `BenchmarkStore`, dò sức
    khoẻ và chính sách lại với nhau. Một lỗi ở đó (truyền một THƯ MỤC vào
    tham số vị trí đầu của `BenchmarkStore`, vốn là một ĐƯỜNG DẪN TỆP) ném
    `PermissionError`, bị `_khoi_hoi_dong` nuốt vào `REASONING_ERROR`, và
    hội đồng KHÔNG BAO GIỜ chạy — trong khi 102 bài kiểm khác vẫn xanh. Đã
    xảy ra thật.
    """

    def setUp(self):
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path

        from scripts.control_center.engine import ControlCenter
        from scripts.control_center.model import Project

        self.goc = Path(tempfile.mkdtemp(prefix="cc-v08-wire-"))
        (self.goc / "docs").mkdir(parents=True)
        (self.goc / "docs" / "a.md").write_text("x\n", encoding="utf-8")
        for c in (["git", "init", "-q"], ["git", "config", "user.email", "t@l"],
                  ["git", "config", "user.name", "t"], ["git", "add", "-A"],
                  ["git", "commit", "-q", "-m", "seed"]):
            subprocess.run(c, cwd=self.goc, check=True, capture_output=True)
        self._rmtree = shutil.rmtree
        self.gia = BoGoiGia(kich_ban={
            VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL_OK, giay=3.0)],
            VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB_OK, giay=2.0)]})
        self.cc = ControlCenter(root=self.goc, probe=False,
                                bo_goi_vai=self.gia)
        self.cc.them_project(Project(project_id="w", name="W",
                                     repo_path=str(self.goc)))

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        self._rmtree(self.goc, ignore_errors=True)

    def _loi(self):
        return [e for e in self.cc.store.su_kien(project_id="w", limit=100)
                if e["kind"] == "REASONING_ERROR"]

    def test_luot_tam_thuong_khong_goi_model_va_khoi_RONG(self):
        bg = self.cc.leader_ban_ghi("w")
        self.assertEqual(self.cc._khoi_hoi_dong("w", F, bg, khoi={}), "")
        self.assertEqual(self.gia.da_goi, [])
        self.assertEqual(self._loi(), [])

    def test_luot_kho_CHAY_THAT_qua_engine(self):
        bg = self.cc.leader_ban_ghi("w")
        khoi = self.cc._khoi_hoi_dong(
            "w", E, bg, khoi={"vien_nang": "vn", "ky_uc": "ku"})
        self.assertEqual(self._loi(), [],
                         "hội đồng không được chết âm thầm vào REASONING_ERROR")
        self.assertEqual(len(self.gia.da_goi), 2,
                         "Strategist và Reviewer phải THẬT SỰ được gọi")
        self.assertIn("KẾT QUẢ HỘI ĐỒNG SUY LUẬN", khoi)
        self.assertIn("REVISE", khoi)

        ng = self.cc.nguon_goc_suy_luan("w")
        self.assertTrue(ng["da_chay"])
        self.assertEqual(len(ng["nguon_goc"]), 2)
        for n in ng["nguon_goc"]:
            self.assertEqual(n["trang_thai"], "OK")
            self.assertTrue(n["ngu_canh"]["ten_khoi_da_cap"])
            self.assertLessEqual(n["ngu_canh"]["token"],
                                 n["ngu_canh"]["tran_token"])

    def test_snapshot_mang_ban_GON(self):
        bg = self.cc.leader_ban_ghi("w")
        self.cc._khoi_hoi_dong("w", E, bg, khoi={"vien_nang": "vn"})
        s = self.cc.snapshot("w")["suy_luan"]
        self.assertTrue(s["da_chay"])
        self.assertTrue(s["dong"])
        self.assertNotIn("nguon_goc", s, "bản GỌN, không nhồi cả Decision")

    def test_dat_che_do_BEN_va_FAIL_CLOSED(self):
        self.assertEqual(self.cc.dat_che_do("w", "max")["che_do"], "MAX")
        self.assertEqual(self.cc.leader_ban_ghi("w").che_do, "MAX")
        with self.assertRaises(ValueError):
            self.cc.dat_che_do("w", "TURBO")
        self.assertEqual(self.cc.leader_ban_ghi("w").che_do, "MAX")

    def test_chinh_sach_du_an_trong_thi_FAIL_CLOSED(self):
        cs = self.cc.chinh_sach_cao_cap("w")
        self.assertTrue(cs.han_che)
        self.assertNotEqual(cs.nguon, "ky_uc")

    def test_luot_vai_DUOC_GHI_vao_lich_su_benchmark(self):
        """Vòng phản hồi: `benchmark_profile` phải chuyển từ tiên nghiệm cấu
        hình sang số ĐO ĐƯỢC. Không có dòng ghi này thì tiên nghiệm là vĩnh
        viễn — đúng giới hạn v0.8 tự nêu."""
        from scripts.router_v4.history import BenchmarkStore, duong_vai

        bg = self.cc.leader_ban_ghi("w")
        self.cc._khoi_hoi_dong("w", E, bg, khoi={"vien_nang": "vn"})

        ls = BenchmarkStore(path=duong_vai(self.goc))
        ds = ls.all()
        self.assertEqual(len(ds), 2, "một bản ghi cho MỖI vai đã chạy")
        loai = {r.task_type for r in ds}
        self.assertEqual(loai, {"reasoning_strategist", "reasoning_reviewer"})
        for r in ds:
            with self.subTest(t=r.task_type):
                self.assertTrue(r.success)
                self.assertTrue(r.model_id and r.provider and r.runtime_id)
                self.assertEqual(r.project, "w")
                self.assertGreater(r.wall_seconds, 0.0)
                # KHONG DO DUOC -> None, khong bao gio 0.
                self.assertIsNone(r.tokens)
                self.assertIsNone(r.cost_usd)
                self.assertIsNone(r.quality, "rubric do người chấm, không tự bịa")
                self.assertTrue(r.rubric, "phải trỏ tới chỗ ghi rubric")
        rv = next(r for r in ds if r.task_type == "reasoning_reviewer")
        self.assertEqual(rv.verdict, "REVISE")
        self.assertGreater(rv.review_findings, 0)

    def test_lich_su_vai_KHONG_tron_vao_lich_su_worker(self):
        from scripts.router_v4.history import BenchmarkStore, duong, duong_vai

        bg = self.cc.leader_ban_ghi("w")
        self.cc._khoi_hoi_dong("w", E, bg, khoi={"vien_nang": "vn"})
        self.assertTrue(duong_vai(self.goc).exists())
        self.assertEqual(BenchmarkStore(path=duong(self.goc)).all(), [],
                         "lịch sử worker phải KHÔNG bị lượt suy luận chạm vào")

    def test_du_mau_thi_lich_su_LAN_AT_tien_nghiem(self):
        """Ba mẫu là `MAU_TOI_THIEU`; từ đó `summary_for` trả số thật."""
        from scripts.router_v4.history import BenchmarkStore, duong_vai

        bg = self.cc.leader_ban_ghi("w")
        for _ in range(3):
            self.gia.kich_ban[VaiTro.STRATEGIST] = [
                LuotVai(ok=True, van_ban=CL_OK, giay=3.0)]
            self.gia.kich_ban[VaiTro.REVIEWER] = [
                LuotVai(ok=True, van_ban=PB_OK, giay=2.0)]
            self.cc._khoi_hoi_dong("w", E, bg, khoi={"vien_nang": "vn"})
        ls = BenchmarkStore(path=duong_vai(self.goc))
        s = ls.summary_for(task_type="reasoning_strategist",
                           model_id=ls.all()[0].model_id)
        self.assertIsNotNone(s, "≥3 mẫu thì phải có tổng hợp ĐO ĐƯỢC")
        self.assertGreaterEqual(s["samples"], 3)
        self.assertEqual(s["success_rate"], 1.0)


if __name__ == "__main__":                                  # pragma: no cover
    unittest.main()
