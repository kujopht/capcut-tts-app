"""API + giao diện của ký ức (V0.6) — những điều CI phải cưỡng chế.

1. Mọi đường ĐỌC là GET, đi qua `_sach` (lọc bí mật), đòi token như mọi
   `/api/*` khác (rào V0.2 không đổi).
2. KHÔNG có endpoint xoá lịch sử; KHÔNG handler nào tên `blob`.
3. Đường ghi chỉ chạm sổ ký ức của chính Control Center.
4. `veHet()` (vòng vẽ 1 Hz) KHÔNG gọi một hàm ký ức nào — thống kê là
   `count(*)` trên một sổ có thể rất lớn.
5. Tab Memory có mặt, và các bộ lọc yêu cầu (Timeline / Decisions /
   Incidents / Checkpoints / Architecture) có mặt.
"""
from __future__ import annotations

import ast
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from scripts.control_center.engine import ControlCenter
from scripts.control_center.model import Project
from scripts.control_center.store import ControlStore
from scripts.control_center.webapi import PhienWeb, dung_app

GOC = Path(__file__).resolve().parents[2]
WEB = GOC / "scripts" / "control_center" / "web"
WEBAPI = GOC / "scripts" / "control_center" / "webapi.py"


class _Nen(unittest.TestCase):
    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-memapi-"))
        self.st = ControlStore(root=self.goc)
        self.cc = ControlCenter(store=self.st, root=self.goc, probe=False)
        self.cc.them_project(Project(project_id="p", name="P",
                                     repo_path=str(self.goc)))
        self.phien = PhienWeb(self.cc, token="t0ken", cong=1)
        self.app = dung_app(self.phien)
        self.c = TestClient(self.app, base_url="http://127.0.0.1")
        self.h = {"X-CC-Token": "t0ken"}

    def tearDown(self):
        try:
            self.cc.shutdown()
        except Exception:                                   # noqa: BLE001
            pass
        self.st.close()
        shutil.rmtree(self.goc, ignore_errors=True)


class TestDuongDoc(_Nen):
    def test_stats_search_timeline_list_record_continue_context(self):
        self.cc.ky_uc.ghi_quyet_dinh("p", "Giữ legacy chỉ đọc.", ly_do="an toàn",
                                     tieu_de="legacy")
        self.st.them_chat("p", "user", "farmer restart hôm qua")
        r = self.c.get("/api/memory/stats?project=p", headers=self.h)
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["san_sang"])
        self.assertGreaterEqual(d["dem"]["su_kien"], 2)
        for k in ("lich_su_tho", "bang_chung", "co_cau_truc", "chi_muc", "tong"):
            self.assertIn(k, d["byte"])

        r = self.c.get("/api/memory/search?project=p&q=legacy", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ket_qua"])

        r = self.c.get("/api/memory/timeline?project=p", headers=self.h)
        self.assertTrue(r.json()["su_kien"])

        r = self.c.get("/api/memory/list?project=p&loai=decision", headers=self.h)
        qd = r.json()["ket_qua"]
        self.assertEqual(len(qd), 1)
        ma = qd[0]["ma"]

        r = self.c.get(f"/api/memory/record?project=p&ma={ma}", headers=self.h)
        self.assertTrue(r.json()["co"])
        self.assertEqual(r.json()["quyet_dinh"]["ma"], ma)
        self.assertTrue(r.json()["bang_chung"], "quyết định phải có nguồn gốc L0")

        r = self.c.get("/api/memory/continue?project=p", headers=self.h)
        self.assertTrue(r.json()["san_sang"])
        self.assertEqual(len(r.json()["quyet_dinh_hieu_luc"]), 1)

        r = self.c.get("/api/memory/context?project=p&q=legacy", headers=self.h)
        d = r.json()
        self.assertLessEqual(d["token_uoc"], d["token_tran"])
        self.assertIn("KÝ ỨC DỰ ÁN", d["van"])

    def test_stats_khong_project_la_toan_cuc(self):
        r = self.c.get("/api/memory/stats", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertIn("du_an", r.json())

    def test_evidence_thieu_thi_noi_thieu(self):
        r = self.c.get("/api/memory/evidence?project=p&su_kien_id=999999",
                       headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["co"])
        self.assertIn("không có sự kiện", r.json()["ly_do"])


class TestDuongGhi(_Nen):
    def test_checkpoint_decision_record_capsule(self):
        r = self.c.post("/api/memory/decision", headers=self.h,
                        json={"project": "p", "noi_dung": "Dùng FTS5.",
                              "ly_do": "đủ", "tieu_de": "fts"})
        self.assertEqual(r.status_code, 200)
        q1 = r.json()["ma"]
        r = self.c.post("/api/memory/decision", headers=self.h,
                        json={"project": "p", "noi_dung": "Thêm vector.",
                              "thay_the_cho": [q1]})
        self.assertEqual(r.json()["thay_the_cho"], [q1])
        r = self.c.post("/api/memory/record", headers=self.h,
                        json={"project": "p", "loai": "architecture",
                              "noi_dung": "Web trên Worker.", "tieu_de": "web"})
        self.assertEqual(r.json()["loai"], "architecture")
        r = self.c.post("/api/memory/checkpoint", headers=self.h,
                        json={"project": "p", "ly_do": "handoff",
                              "noi_dung": {"muc_tieu": "xong UI",
                                           "chua_xong": "EXE\nacceptance"}})
        self.assertEqual(r.json()["muc_tieu"], "xong UI")
        self.assertEqual(r.json()["chua_xong"], ["EXE", "acceptance"])
        r = self.c.post("/api/memory/capsule", headers=self.h,
                        json={"project": "p", "thay_doi": {"muc_tieu": "ship"},
                              "ly_do": "khởi tạo"})
        self.assertEqual(r.json()["muc_tieu"], "ship")
        self.assertGreaterEqual(r.json()["phien_ban"], 1)

    def test_thieu_project_hoac_noi_dung_thi_400(self):
        for duong, than in (("/api/memory/decision", {"noi_dung": "x"}),
                            ("/api/memory/decision", {"project": "p"}),
                            ("/api/memory/record", {"project": "p"}),
                            ("/api/memory/checkpoint", {}),
                            ("/api/memory/capsule", {})):
            with self.subTest(duong=duong):
                r = self.c.post(duong, headers=self.h, json=than)
                self.assertEqual(r.status_code, 400)


class TestRaoV02KhongDoi(_Nen):
    def test_khong_token_thi_401_ke_ca_GET(self):
        for d in ("/api/memory/stats?project=p", "/api/memory/search?project=p&q=x",
                  "/api/memory/timeline?project=p", "/api/memory/continue?project=p"):
            with self.subTest(duong=d):
                self.assertEqual(self.c.get(d).status_code, 401)

    def test_host_la_thi_400_truoc_token(self):
        r = self.c.get("/api/memory/stats?project=p",
                       headers={**self.h, "host": "evil.example"})
        self.assertEqual(r.status_code, 400)

    def test_payload_ra_qua_bo_loc_bi_mat(self):
        bm = "ghp_" + "z" * 40
        # Di thang vao so ky uc, bo qua bo loc cua store — de kiem `_sach`.
        p = self.cc.ky_uc.provider("p")
        from scripts.control_center.memory.model import KyUc, LoaiKyUc
        # Ky uc tu loc o cong vao; nhung `_sach` van la lop cuoi. Giả lập
        # bằng cách chèn thẳng SQL một dòng có bí mật.
        import sqlite3
        c = sqlite3.connect(str(p.kho.path))
        c.execute("INSERT INTO ky_uc (ma, loai, tieu_de, noi_dung, chuan, quan_trong, "
                  "tin_cay, ts, ts_su_kien, ts_cham, han_tuoi) VALUES "
                  "('ku_test', 'semantic', 't', ?, 'x', 5, 'ghi_nhan', 1, 1, 1, 0)", (bm,))
        c.commit(); c.close()
        r = self.c.get("/api/memory/record?project=p&ma=ku_test", headers=self.h)
        self.assertNotIn(bm, r.text)
        self.assertIn("[DA-LOC]", r.text)


class TestMaNguon(unittest.TestCase):
    def test_duong_doc_chi_GET_va_khong_co_endpoint_xoa(self):
        src = WEBAPI.read_text(encoding="utf-8")
        # Bat dau tu HANDLER dau tien, bo qua ham phu `_ky_uc()` (no tra ve
        # dich vu, khong tra ve payload).
        i = src.index('@app.get("/api/memory/stats")')
        j = src.index("# -- cai dat giao dien")
        vung = src[i:j]
        self.assertNotIn("@app.delete", vung)
        self.assertNotIn("@app.put", vung)
        self.assertNotIn("@app.patch", vung)
        for m in re.finditer(r'@app\.post\("(/api/memory/[a-z_]+)"\)', vung):
            self.assertIn(m.group(1), ("/api/memory/checkpoint", "/api/memory/decision",
                                       "/api/memory/record", "/api/memory/capsule"))
        self.assertNotIn("def blob", vung)
        # Moi `return` O MUC HANDLER (8 khoang trang) deu qua `_sach` hoac
        # `_ma_loi`. Ham con ben trong (12+ khoang) tra ve du lieu tho cho
        # handler roi handler moi loc — nen khong xet chung.
        for dong in vung.splitlines():
            if dong.startswith("        return ") and not dong.startswith("         "):
                s = dong.strip()
                if "_ma_loi" not in s:
                    self.assertIn("_sach(", s, s)

    def test_veHet_khong_goi_ky_uc(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        i = js.index("function veHet()")
        than = js[i:i + 1400]
        for ham in ("veKyUc", "veKyUcThongKe", "veKyUcDanhSach", "/api/memory"):
            self.assertNotIn(ham, than, f"`veHet` không được gọi {ham}")

    def test_tab_va_bo_loc_co_mat(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-khung="kyuc"', html)
        for loc in ("timeline", "decision", "incident", "checkpoint", "architecture"):
            self.assertIn(f'data-loc="{loc}"', html)
        self.assertIn('id="kyuc-tim"', html)

    def test_doiKhung_mo_tab_ky_uc_moi_lam_moi(self):
        js = (WEB / "app.js").read_text(encoding="utf-8")
        i = js.index("function doiKhung(")
        self.assertIn("if (ten === 'kyuc') veKyUc();", js[i:i + 600])

    def test_ui_khong_co_nut_xoa_lich_su(self):
        """`permissions.py` gắn cổng GATED cho "xoá lịch sử"/"xoá dữ liệu";
        giao diện ký ức V0.6 không có hành động nào như thế — và không
        được có, vì L0 là chỉ-thêm."""
        html = (WEB / "index.html").read_text(encoding="utf-8")
        i = html.index('id="khung-kyuc"')
        j = html.index("</section>", i)
        vung = html[i:j].lower()
        for x in ("xoá lịch sử", "xoa lich su", "xoá dữ liệu", "delete history",
                  "clear memory"):
            self.assertNotIn(x, vung)

    def test_engine_ghi_MEMORY_CONTEXT_khi_co_khoi(self):
        src = (GOC / "scripts" / "control_center" / "engine.py").read_text(encoding="utf-8")
        self.assertIn('"MEMORY_CONTEXT"', src)
        self.assertIn("khoi_ky_uc=khoi_ky_uc", src)


class TestDesktopDongNhe(unittest.TestCase):
    """Đóng cửa sổ PHẢI tới được `cc.shutdown()` — khuyết tật V0.2 lộ ở V0.6.

    Đo thật trên bản EXE: nhật ký có "đang tắt backend…" nhưng KHÔNG có
    `ENGINE_STOPPED` — `webview.start()` trả về ngay khi cửa sổ đóng, còn
    `events.closed` chạy trên luồng nền và bị giết khi `main()` kết thúc.
    Hai điều phải giữ: `main()` CHỜ (có hạn) luồng đóng; và `shutdown()`
    đứng TRƯỚC `join` uvicorn trong `_khi_dong`.
    """

    def setUp(self):
        self.src = (GOC / "scripts" / "control_center" / "desktop.py").read_text(
            encoding="utf-8")

    def test_main_cho_luong_dong_sau_webview_start(self):
        i = self.src.index("webview.start(gui=")
        duoi = self.src[i:i + 1200]
        self.assertIn("da_dong.wait(timeout=", duoi,
                      "main() phải chờ `_khi_dong` xong sau `webview.start()`")

    def test_khi_dong_goi_shutdown_TRUOC_join_uvicorn(self):
        i = self.src.index("def _khi_dong():")
        than = self.src[i:i + 2000]
        self.assertLess(than.index("cc.shutdown()"), than.index("luong.join("),
                        "shutdown (điểm dừng, Leader) phải chạy trước khi chờ uvicorn")
        self.assertIn("da_dong.set()", than)
        self.assertIn("finally:", than)


class TestEngineTichHop(_Nen):
    def test_engine_mo_ky_uc_va_ghi_MEMORY_RESUMED_khi_co_gi(self):
        self.cc.ky_uc.diem_dung_tuong_minh("p", "x", {"muc_tieu": "tiếp"})
        self.cc.shutdown(); self.st.close()
        st2 = ControlStore(root=self.goc)
        cc2 = ControlCenter(store=st2, root=self.goc, probe=False)
        ev = [e for e in st2.su_kien(project_id="p", limit=50)
              if e["kind"] == "MEMORY_RESUMED"]
        self.assertTrue(ev)
        self.assertIn("điểm dừng", ev[0]["detail"])
        cc2.shutdown(); st2.close()
        self.st = ControlStore(root=self.goc)
        self.cc = ControlCenter(store=self.st, root=self.goc, probe=False)

    def test_shutdown_ghi_diem_dung_tat_ung_dung(self):
        self.st.them_chat("p", "user", "làm việc")
        self.cc.shutdown()
        st2 = ControlStore(root=self.goc)
        from scripts.control_center.memory.service import DichVuKyUc
        dv = DichVuKyUc(st2, self.goc)
        dds = dv.provider("p").cac_diem_dung()
        self.assertTrue(any(d.ly_do == "tắt ứng dụng" for d in dds))
        dv.close(); st2.close()

    def test_ky_uc_hong_khong_giet_engine(self):
        goc = Path(tempfile.mkdtemp(prefix="cc-memhong-"))
        try:
            st = ControlStore(root=goc)
            # Chan thu muc ky uc bang MOT TEP.
            (goc / ".router" / "memory").write_text("chặn", encoding="utf-8")
            cc = ControlCenter(store=st, root=goc, probe=False)
            cc.them_project(Project(project_id="p", name="P", repo_path=str(goc)))
            # Router van chay: chat khong Leader -> phan ra truc tiep.
            self.assertIsNotNone(cc.snapshot("p"))
            m = st.them_chat("p", "user", "vẫn ghi được")
            self.assertGreater(m.message_id, 0)
            self.assertEqual(cc._khoi_ky_uc("p", "x"), "")
            cc.shutdown(); st.close()
        finally:
            shutil.rmtree(goc, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
