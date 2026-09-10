# -*- coding: utf-8 -*-
"""V0.6.1 — KÝ ỨC LÀM ĐẦU (memory-first Leader) + NHẤT QUÁN KHO (khuyết tật
nghiệm thu tay 2026-09-10).

Hai khuyết tật thật:

1. Người dùng gõ tuyên bố quyết định tường minh, tab Memory vẫn `Decisions=0`.
   Nguyên nhân THẬT: gõ vào một bản EXE CŨ (V0.6, chưa có `de_bat`) + tách kho
   theo gốc `.router` (mỗi bản dựng/checkout một sổ). Mã V0.6.1 HIỆN TẠI đề bạt
   đúng — bài `test_de_bat_...` khoá điều đó; ở đây khoá thêm rằng ĐỌC (UI) và
   GHI (chat) và LEADER cùng trỏ MỘT sổ.
2. "cái vụ SSH key … trước đây bị gì?" -> Leader tạo việc, dispatch AG02 200s.
   Đó KHÔNG phải memory recall. `la_cau_hoi_lich_su` + `LUAT_LICH_SU` lật mặc
   định: câu hỏi lịch sử -> trả từ ký ức, đính bằng chứng L0, không tự dispatch.

Không LLM, không mạng: oracle là chính `DichVuKyUc` trên kho tạm.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center import leader                              # noqa: E402
from scripts.control_center.memory.model import (SuKien,               # noqa: E402
                                                 khong_gian_ten)
from scripts.control_center.memory.service import (DichVuKyUc,          # noqa: E402
                                                   duong_goc_ky_uc)
from scripts.control_center.model import Project                       # noqa: E402
from scripts.control_center.store import ControlStore                  # noqa: E402

CAU_DECISION = ("hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được "
                "dùng cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc "
                "định cho task thường.")


# =========================================================== phat hien =====

class TestPhatHienLichSu(unittest.TestCase):

    def test_cau_lich_su_va_kien_thuc_du_an(self):
        for cau in ("cái vụ SSH key fanficappwrite trước đây bị gì?",
                    "policy GPT-6 Astra của project này là gì?",
                    "vì sao lần trước deploy bị lỗi?",
                    "quyết định của dự án về routing là gì?",
                    "what happened with the SSH key?",
                    "rule của project là gì?"):
            with self.subTest(cau=cau):
                r, dh = leader.la_cau_hoi_lich_su(cau)
                self.assertTrue(r, f"phải là câu hỏi lịch sử: {cau} · {dh}")

    def test_khong_phai_lich_su(self):
        for cau in ("sửa lỗi trong web/admin", "gọi 4 agent kiểm tra repo",
                    "ê bro khỏe không", "production farmer còn chạy không?",
                    "chạy test đi", ""):
            with self.subTest(cau=cau):
                r, _ = leader.la_cau_hoi_lich_su(cau)
                self.assertFalse(r, f"KHÔNG phải câu hỏi lịch sử: {cau}")

    def test_luat_lich_su_chi_khi_lich_su_va_co_khoi(self):
        # Sentinel RIENG cua than LUAT_LICH_SU (khac cum trong HUONG_DAN rule 7).
        SEN = "Ký ức dự án là nơi tra lịch sử"
        self.assertIn(SEN, leader.LUAT_LICH_SU)
        anh = type("A", (), {"tom_tat": lambda self: "trạng thái"})()
        nn = leader.dung_nhac_nho(anh, [], "cái vụ X trước đây bị gì?",
                                  khoi_ky_uc="KÝ ỨC: [ku_1] X", la_lich_su=True)
        self.assertIn(SEN, nn)
        self.assertIn(leader.LUAT_KY_UC[:20], nn)          # van co luat ky uc chung
        # Khong lich su -> khong nhet than LUAT_LICH_SU.
        nn2 = leader.dung_nhac_nho(anh, [], "sửa web", khoi_ky_uc="KÝ ỨC: ...",
                                   la_lich_su=False)
        self.assertNotIn(SEN, nn2)
        # Lich su nhung KHONG co khoi ky uc -> khong nhet luat (khong co gi de tra).
        nn3 = leader.dung_nhac_nho(anh, [], "cái vụ X trước đây bị gì?",
                                   khoi_ky_uc="", la_lich_su=True)
        self.assertNotIn(SEN, nn3)


# ===================================================== bang chung L0 =======

class _Kho(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cc-kyuc-first-"))
        self.st = ControlStore(root=self.root)
        self.st.luu_project(Project(project_id="fanfic", name="Fanfic",
                                    repo_path=str(self.root)))
        self.dv = DichVuKyUc(self.st, self.root)

    def tearDown(self):
        self.dv.close()
        self.st.close()
        shutil.rmtree(self.root, ignore_errors=True)


class TestBangChungL0(_Kho):

    def test_kem_su_kien_dinh_dong_L0_khop_cau(self):
        p = self.dv.provider("fanfic")
        # Gieo mot dong L0 mang bang chung SSH.
        p.ghi_su_kien(SuKien(loai="backfill:git", ts=time.time(),
                             tom_tat="fanficappwrrite.pem sai tên: mã tham chiếu "
                                     "~/.ssh/fanficappwrrite.pem nhưng khoá thật là "
                                     "fanficappwrite.pem — SSH gãy",
                             nguon="git"),
                      noi_dung_day="chi tiết incident SSH")
        # Khong kem su kien -> khoi co the rong (chua co ky uc lien quan).
        khong = self.dv.khoi_cho_leader("fanfic", "cái vụ SSH key fanficappwrite bị gì?")
        co = self.dv.khoi_cho_leader("fanfic", "cái vụ SSH key fanficappwrite bị gì?",
                                     kem_su_kien=True)
        self.assertIn("BẰNG CHỨNG L0 KHỚP CÂU HỎI", co)
        self.assertIn("sk#", co)
        self.assertIn("fanficappwrrite", co)
        self.assertNotIn("BẰNG CHỨNG L0 KHỚP CÂU HỎI", khong)

    def test_khong_khop_thi_khong_dinh(self):
        co = self.dv.khoi_cho_leader("fanfic", "một câu chả liên quan gì hết",
                                     kem_su_kien=True)
        # Khong co su kien nao khop -> khong co section L0 (co the rong ca khoi).
        self.assertNotIn("BẰNG CHỨNG L0 KHỚP CÂU HỎI", co)


# ================================================= de bat qua chat =========

class TestDeBatQuaChat(_Kho):
    """Ghi (chat) -> đề bạt qd_ đồng bộ; Đọc (UI liet_ke) thấy ngay."""

    def test_tuyen_bo_thanh_quyet_dinh_va_UI_thay(self):
        self.st.them_chat("fanfic", role="user", text=CAU_DECISION)
        time.sleep(0.1)
        ui = self.dv.liet_ke("fanfic", "decision")
        self.assertEqual(len(ui["ket_qua"]), 1, "UI Decision count phải = 1 ngay")
        d = ui["ket_qua"][0]
        k = d["ky_uc"]
        self.assertEqual(k["tin_cay"], "user_explicit")
        self.assertIn("Astra", k["noi_dung"])
        self.assertEqual(k["nguon_loai"], "chat_user")
        self.assertTrue(k["bang_chung"], "phải có mắt xích bằng chứng về dòng L0")

    def test_cau_hoi_khong_thanh_quyet_dinh(self):
        self.st.them_chat("fanfic", role="user",
                          text="policy GPT-6 Astra của project này là gì?")
        time.sleep(0.05)
        self.assertEqual(len(self.dv.liet_ke("fanfic", "decision")["ket_qua"]), 0)


# ============================================= NHAT QUAN KHO (buoc 11) =====

class TestNhatQuanKho(_Kho):
    """Bốn đường — ghi chat, backfill, UI, truy hồi Leader — MỘT sổ."""

    def _duong_db_provider(self, pid: str) -> Path:
        # LocalMemoryProvider giữ kho ở `<goc>/.router/memory/<ns>/memory.db`.
        return Path(self.dv.provider(pid).thu_muc) / "memory.db"

    def test_bon_duong_cung_mot_namespace_va_so(self):
        pid = "fanfic"
        ns = khong_gian_ten(pid)
        db = self._duong_db_provider(pid)
        self.assertEqual(db.parent.name, ns)
        self.assertTrue(db.parent.parent.samefile(duong_goc_ky_uc(self.root)))
        self.assertTrue(db.parent.parent.samefile(self.root / ".router" / "memory"))

        # (a) GHI chat: đề bạt một quyết định.
        self.st.them_chat("fanfic", role="user", text=CAU_DECISION)
        time.sleep(0.1)
        # (b) BACKFILL: cùng provider (cùng project) — kiểm bộ nhập dùng đúng sổ.
        bo = self.dv._bo_nhap_khau(pid)
        self.assertIsNotNone(bo)
        self.assertEqual(bo.p, self.dv.provider(pid), "backfill dùng ĐÚNG provider")
        # (c) UI đọc: liet_ke decision.
        ui = self.dv.liet_ke(pid, "decision")["ket_qua"]
        self.assertEqual(len(ui), 1)
        qd_ma = ui[0]["ma"]
        # (d) LEADER truy hồi: khối ký ức thấy đúng quyết định vừa ghi.
        khoi = self.dv.khoi_cho_leader(pid, "quyết định Astra của project là gì?")
        self.assertIn("Astra", khoi)

        # TAT CA doc tu MOT tep vat ly: mo truc tiep bang sqlite, thay qd.
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        n = con.execute("SELECT COUNT(*) FROM quyet_dinh").fetchone()[0]
        con.close()
        self.assertEqual(n, 1, "sổ vật lý phải có đúng 1 quyết định — cùng nơi UI/Leader đọc")
        # provider.ns khop namespace tinh tu project_id.
        self.assertEqual(self.dv.provider(pid).ns, ns)

    def test_project_id_khac_thi_so_khac(self):
        self.assertNotEqual(khong_gian_ten("fanfic"), khong_gian_ten("router"))
        # Doc project fanfic khong thay ky uc cua project router.
        self.st.luu_project(Project(project_id="router", name="Router",
                                    repo_path=str(self.root)))
        self.st.them_chat("router", role="user", text=CAU_DECISION)
        time.sleep(0.05)
        self.assertEqual(len(self.dv.liet_ke("fanfic", "decision")["ket_qua"]), 0)
        self.assertEqual(len(self.dv.liet_ke("router", "decision")["ket_qua"]), 1)


if __name__ == "__main__":
    unittest.main()
