"""V0.6.1 — đề bạt tuyên bố tường minh, thay thế, nguồn gốc, lược đồ v2.

Khuyết tật gốc (nghiệm thu tay bản EXE V0.6): "hãy ghi nhớ đây là một quyết
định của project: …" được lưu ở L0 nhưng `Decisions = 0`. Mỗi bài ở đây
là một cạnh của cách sửa.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from scripts.control_center.memory import DichVuKyUc, KyUc, LoaiKyUc, TinCay
from scripts.control_center.memory import de_bat
from scripts.control_center.memory.kho import COT_V2, PHIEN_BAN_LUOC_DO, KhoKyUc
from scripts.control_center.memory.model import TrangThaiKyUc
from scripts.control_center.model import Project
from scripts.control_center.store import ControlStore

ASTRA = ("hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra chỉ được "
         "dùng cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc "
         "định cho task thường.")


class _Nen(unittest.TestCase):
    def setUp(self):
        self.goc = Path(tempfile.mkdtemp(prefix="cc-v061-"))
        self.st = ControlStore(root=self.goc)
        self.dv = DichVuKyUc(self.st, self.goc)
        self.st.luu_project(Project(project_id="router", name="R", repo_path=str(self.goc)))
        self.st.luu_project(Project(project_id="fanfic", name="F", repo_path=str(self.goc)))

    def tearDown(self):
        self.dv.close(); self.st.close()
        shutil.rmtree(self.goc, ignore_errors=True)


class TestPhanLoaiTuyenBo(unittest.TestCase):
    def test_astra_la_quyet_dinh(self):
        kq = de_bat.xet(ASTRA)
        self.assertIsNotNone(kq)
        self.assertIs(kq.loai, LoaiKyUc.DECISION)
        self.assertTrue(kq.noi_dung.startswith("GPT-6 Astra"))
        self.assertFalse(kq.muon_thay_the)

    def test_cac_loai_khac(self):
        cases = {
            "Từ giờ rule là: mọi PR phải có test trước khi merge.": LoaiKyUc.CONSTRAINT,
            "Constraint của project: không được deploy production từ máy dev.": LoaiKyUc.CONSTRAINT,
            "Requirement: worker phải chạy được offline.": LoaiKyUc.REQUIREMENT,
            "Đây là sự cố: SSH key sai tên, đã sửa bằng khoá canonical.": LoaiKyUc.INCIDENT,
            "Quy trình: để build EXE thì chạy python scripts/build_desktop_exe.py.": LoaiKyUc.PROCEDURAL,
            "Ghi nhớ giúp: pipeline TTS dùng registry provider.": LoaiKyUc.FACT,
            "remember that the farmer runs on AWS as a systemd unit": LoaiKyUc.FACT,
            "we decided to keep the legacy archive read-only": LoaiKyUc.DECISION,
        }
        for cau, loai in cases.items():
            with self.subTest(cau=cau[:40]):
                kq = de_bat.xet(cau)
                self.assertIsNotNone(kq, cau)
                self.assertIs(kq.loai, loai)

    def test_KHONG_de_bat_cau_thuong(self):
        """Không có dấu hiệu tuyên bố -> None, kể cả khi có 'không được'."""
        for cau in ("Chào Leader, hôm nay làm gì?", "không được quên tắt máy nhé",
                    "chạy test đi", "ok", "tôi nghĩ nên dùng FTS5"):
            with self.subTest(cau=cau):
                self.assertIsNone(de_bat.xet(cau))

    def test_cat_cum_mo_dau(self):
        kq = de_bat.xet("Ghi nhớ giúp: pipeline TTS dùng registry provider.")
        self.assertTrue(kq.noi_dung.lower().startswith("pipeline tts"), kq.noi_dung)

    def test_dau_hieu_thay_the_va_ma_tuong_minh(self):
        kq = de_bat.xet("chúng ta quyết định thay thế quyết định trước: Astra dùng thêm cho review.")
        self.assertTrue(kq.muon_thay_the)
        kq2 = de_bat.xet("quyết định: bỏ qd_0003, từ giờ Astra dùng cho review")
        self.assertIn("qd_0003", kq2.thay_the_tuong_minh)


class TestDeBatQuaChotStore(_Nen):
    def test_quyet_dinh_tao_qd_voi_nguon_goc_L0(self):
        tin = self.st.them_chat("router", "user", ASTRA)
        p = self.dv.provider("router")
        d = p.dem()
        self.assertEqual(d["quyet_dinh"], 1)
        self.assertEqual(d["ky_uc_decision"], 1)
        self.assertEqual(d["ky_uc_user_explicit"], 1)
        qd = p.cac_quyet_dinh()[0]
        self.assertEqual(qd.ma, "qd_0001")
        self.assertTrue(qd.hieu_luc)
        r = self.dv.ban_ghi("router", qd.ma)
        k = r["ky_uc"]
        self.assertEqual(k["tin_cay"], "user_explicit")
        self.assertEqual(k["trang_thai"], "hieu_luc")
        self.assertEqual(k["nguon_loai"], "chat_user")
        self.assertTrue(k["nguon_id"])
        self.assertIn("GPT-6 Astra", k["noi_dung"])
        # Bang chung tro ve DUNG dong L0 mang nguyen van tin nhan.
        self.assertTrue(r["bang_chung"] and r["bang_chung"][0]["co"])
        sk = r["bang_chung"][0]["su_kien"]
        self.assertEqual(sk["loai"], "chat_user")
        self.assertEqual(sk["tham_chieu"], str(tin.message_id))
        self.assertIn("hãy ghi nhớ", sk["tom_tat"])

    def test_khoi_leader_noi_vua_ghi(self):
        self.st.them_chat("router", "user", ASTRA)
        khoi = self.dv.khoi_cho_leader("router", "Astra dùng khi nào?")
        self.assertIn("VỪA GHI TỰ ĐỘNG", khoi)
        self.assertIn("qd_0001 (decision)", khoi)

    def test_su_kien_MEMORY_PROMOTED_duoc_ghi(self):
        self.st.them_chat("router", "user", ASTRA)
        ev = [e for e in self.st.su_kien(project_id="router", limit=50)
              if e["kind"] == "MEMORY_PROMOTED"]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["meta"]["ma"], "qd_0001")

    def test_thay_the_CHI_khi_nguoi_dung_noi(self):
        self.st.them_chat("router", "user", ASTRA)
        # Cau moi ve cung chu de nhung KHONG noi thay the -> hai cai cung hieu luc.
        self.st.them_chat("router", "user",
                          "hãy ghi nhớ đây là quyết định: GPT-6 Astra được phép dùng cho "
                          "architecture review.")
        p = self.dv.provider("router")
        self.assertEqual(len(p.cac_quyet_dinh(chi_hieu_luc=True)), 2)
        # Cau noi ro "thay the quyet dinh truoc" -> cai trung tu khoa bi thay.
        self.st.them_chat("router", "user",
                          "chúng ta quyết định thay thế quyết định trước: GPT-6 Astra dùng "
                          "cho architecture review VÀ security review.")
        qds = {q.ma: q for q in p.cac_quyet_dinh()}
        self.assertEqual(len(qds), 3)
        hieu_luc = [q.ma for q in p.cac_quyet_dinh(chi_hieu_luc=True)]
        self.assertEqual(len(hieu_luc), 2, hieu_luc)
        self.assertIn("qd_0003", hieu_luc)
        bi = [q for q in qds.values() if q.bi_thay_the == "qd_0003"]
        self.assertEqual(len(bi), 1)
        # Ban cu VAN tra duoc, noi dung nguyen ven.
        k_cu = p.ky_uc(bi[0].ky_uc_ma)
        self.assertIs(k_cu.trang_thai, TrangThaiKyUc.THAY_THE)
        self.assertIn("Astra", k_cu.noi_dung)
        self.assertTrue(self.dv.tim("router", "Astra architecture")["ket_qua"])

    def test_thay_the_theo_ma_tuong_minh(self):
        self.st.them_chat("router", "user", ASTRA)
        self.st.them_chat("router", "user", "quyết định: thay cho qd_0001, Astra dùng mọi task review.")
        p = self.dv.provider("router")
        q1 = p.quyet_dinh("qd_0001")
        self.assertEqual(q1.bi_thay_the, "qd_0002")
        self.assertFalse(q1.hieu_luc)

    def test_cac_loai_khac_tang_dem_ngay(self):
        self.st.them_chat("router", "user", "Đây là sự cố: SSH key sai tên fanficappwrrite.pem.")
        self.st.them_chat("router", "user", "Constraint của project: không được deploy từ máy dev.")
        self.st.them_chat("router", "user", "Requirement: worker phải chạy offline.")
        self.st.them_chat("router", "user", "Quy trình: để build EXE thì chạy build_desktop_exe.py.")
        self.st.them_chat("router", "user", "Ghi nhớ giúp: pipeline TTS dùng registry provider.")
        d = self.dv.provider("router").dem()
        for k in ("ky_uc_incident", "ky_uc_constraint", "ky_uc_requirement",
                  "ky_uc_procedural", "ky_uc_fact"):
            with self.subTest(k=k):
                self.assertEqual(d[k], 1)
        self.assertEqual(d["ky_uc_user_explicit"], 5)

    def test_cung_tuyen_bo_hai_lan_la_MOT_ban_ghi(self):
        self.st.them_chat("router", "user", ASTRA)
        self.st.them_chat("router", "user", ASTRA)
        p = self.dv.provider("router")
        self.assertEqual(p.dem()["quyet_dinh"], 1)
        self.assertEqual(p.dem()["ky_uc_decision"], 1)

    def test_khong_ro_ri_du_an_khac(self):
        self.st.them_chat("router", "user", ASTRA)
        self.assertEqual(self.dv.provider("fanfic").dem()["quyet_dinh"], 0)
        self.assertEqual(self.dv.tim("fanfic", "Astra")["ket_qua"], [])

    def test_song_sot_mo_lai_va_phien_moi_doc_duoc(self):
        self.st.them_chat("router", "user", ASTRA)
        self.dv.close(); self.st.close()
        st2 = ControlStore(root=self.goc); dv2 = DichVuKyUc(st2, self.goc)
        tt = dv2.tiep_tuc("router")
        self.assertEqual([q["ma"] for q in tt["quyet_dinh_hieu_luc"]], ["qd_0001"])
        kq = dv2.tim("router", "Astra task khó")
        self.assertTrue(any(r["loai"] == "decision" for r in kq["ket_qua"]))
        khoi = dv2.khoi_cho_leader("router", "Astra dùng khi nào?")
        self.assertIn("GPT-6 Astra", khoi)
        self.assertNotIn("VỪA GHI", khoi)          # phien moi: khong con "vua"
        dv2.close(); st2.close()
        self.st = ControlStore(root=self.goc); self.dv = DichVuKyUc(self.st, self.goc)


class TestLeaderRecordMemory(_Nen):
    def test_hanh_dong_hop_le_va_tu_chay(self):
        from scripts.control_center import leader
        self.assertIn("record_memory", leader.HANH_DONG_HOP_LE)
        self.assertIn("record_memory", leader.HANH_DONG_TU_CHAY)
        self.assertIn("record_memory", leader.HUONG_DAN)
        self.assertIn("không ghi lại", leader.HUONG_DAN)

    def test_engine_chay_record_memory_voi_tin_cay_leader(self):
        from scripts.control_center import leader
        from scripts.control_center.engine import ControlCenter
        cc = ControlCenter(store=self.st, root=self.goc, probe=False)
        try:
            a = leader.HanhDong("record_memory", {"loai": "decision",
                                                  "noi_dung": "Dùng FTS5 trước, vector sau.",
                                                  "ly_do": "đủ cho quy mô hiện tại"})
            r = cc._chay_dieu_khien("router", a)
            self.assertIn("ok", r, r)
            p = cc.ky_uc.provider("router")
            qd = p.cac_quyet_dinh()[0]
            k = p.ky_uc(qd.ky_uc_ma)
            self.assertIs(k.tin_cay, TinCay.LEADER)
            self.assertEqual(k.nguon_loai, "leader")
            a2 = leader.HanhDong("record_memory", {"loai": "fact", "noi_dung": ""})
            self.assertIn("loi", cc._chay_dieu_khien("router", a2))
        finally:
            cc.shutdown()


class TestLuocDoV2(unittest.TestCase):
    def test_nang_cap_so_v1_len_v2_giu_du_lieu(self):
        goc = Path(tempfile.mkdtemp(prefix="cc-v1-"))
        try:
            duong = goc / "memory.db"
            # Dung mot so V1 THAT: bang ky_uc khong co cot v2.
            c = sqlite3.connect(str(duong))
            c.executescript("""
                CREATE TABLE ky_uc (id INTEGER PRIMARY KEY AUTOINCREMENT, ma TEXT NOT NULL UNIQUE,
                  loai TEXT NOT NULL, tieu_de TEXT NOT NULL DEFAULT '', noi_dung TEXT NOT NULL,
                  chuan TEXT NOT NULL, quan_trong INTEGER NOT NULL DEFAULT 5,
                  tin_cay TEXT NOT NULL DEFAULT 'ghi_nhan', ts REAL NOT NULL, ts_su_kien REAL NOT NULL,
                  ts_cham REAL NOT NULL, han_tuoi REAL NOT NULL DEFAULT 0,
                  the_json TEXT NOT NULL DEFAULT '[]', meta_json TEXT NOT NULL DEFAULT '{}',
                  da_loc INTEGER NOT NULL DEFAULT 0);
                INSERT INTO ky_uc (ma, loai, tieu_de, noi_dung, chuan, ts, ts_su_kien, ts_cham)
                  VALUES ('ku_cu', 'semantic', 't', 'nội dung cũ', 'noi dung cu', 1, 1, 1);
                PRAGMA user_version = 1;
            """)
            c.commit(); c.close()
            k = KhoKyUc(duong)
            self.assertEqual(k.phien_ban_luoc_do, PHIEN_BAN_LUOC_DO)
            cot = {r[1] for r in k._c().execute("PRAGMA table_info(ky_uc)")}
            for ten, _ in COT_V2:
                self.assertIn(ten, cot)
            cu = k.ky_uc("ku_cu")
            self.assertEqual(cu.noi_dung, "nội dung cũ")
            self.assertIs(cu.trang_thai, TrangThaiKyUc.HIEU_LUC)
            self.assertTrue(cu.hieu_luc)
            # Mo lan hai: idempotent.
            k.close(); k2 = KhoKyUc(duong)
            self.assertEqual(k2.phien_ban_luoc_do, PHIEN_BAN_LUOC_DO); k2.close()
        finally:
            shutil.rmtree(goc, ignore_errors=True)

    def test_thay_the_ky_uc_moi_loai_hai_chieu(self):
        goc = Path(tempfile.mkdtemp(prefix="cc-tt-"))
        try:
            k = KhoKyUc(goc / "m.db")
            a = k.luu_ky_uc(KyUc(loai=LoaiKyUc.CONSTRAINT, noi_dung="A"))
            b = k.luu_ky_uc(KyUc(loai=LoaiKyUc.CONSTRAINT, noi_dung="B"))
            self.assertTrue(k.thay_the_ky_uc(b.ma, a.ma, ai="t"))
            a2, b2 = k.ky_uc(a.ma), k.ky_uc(b.ma)
            self.assertEqual(a2.bi_thay_the, b.ma)
            self.assertIs(a2.trang_thai, TrangThaiKyUc.THAY_THE)
            self.assertIn(a.ma, b2.thay_the_cho)
            self.assertEqual([x.ma for x in k.liet_ke_ky_uc(chi_hieu_luc=True)], [b.ma])
            self.assertFalse(k.thay_the_ky_uc(b.ma, b.ma))
            self.assertFalse(k.thay_the_ky_uc(b.ma, "ku_khong_co"))
            k.close()
        finally:
            shutil.rmtree(goc, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
