"""Sổ việc bền — nhận việc nguyên tử, thử lại có chặn.

Điểm dễ sai nhất của một hàng đợi là `claim()`. Bài kiểm đồng thời ở dưới
chạy nhiều luồng cùng giành MỘT việc và đòi ĐÚNG một luồng thắng.
"""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from scripts.router_v3.pool.store import PoolStore


class _Nen(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.root = Path(self._d.name)
        self.st = PoolStore(root=self.root)

    def tearDown(self):
        self.st.close()
        self._d.cleanup()


class TestVongDoi(_Nen):
    def test_tao_run_va_them_job(self):
        rid = self.st.tao_run(base_sha="abc123")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        j = self.st.job(jid)
        self.assertIsNotNone(j)
        self.assertEqual(j.status, "queued")
        self.assertEqual(j.node_id, "A")
        self.assertEqual(self.st.run(rid)["base_sha"], "abc123")

    def test_claim_ghi_worker_va_tang_luot(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.assertTrue(self.st.claim(jid, "AG01"))
        j = self.st.job(jid)
        self.assertEqual(j.status, "running")
        self.assertEqual(j.worker_id, "AG01")
        self.assertEqual(j.attempt, 1)
        self.assertEqual(j.tried, ["AG01"])

    def test_claim_lan_hai_that_bai(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.assertTrue(self.st.claim(jid, "AG01"))
        self.assertFalse(self.st.claim(jid, "AG02"))

    def test_claim_dong_thoi_chi_mot_ben_thang(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        thang = []
        rao = threading.Barrier(8)

        def thu(i):
            # Moi luong mot ket noi rieng — dung y het daemon that.
            st = PoolStore(root=self.root)
            rao.wait()
            if st.claim(jid, f"W{i}"):
                thang.append(i)
            st.close()

        ts = [threading.Thread(target=thu, args=(i,)) for i in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(thang), 1, f"phải đúng 1 bên thắng, được {thang}")

    def test_hoan_thanh_luu_phong_bi(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.st.claim(jid, "AG01")
        self.st.hoan_thanh(jid, status="ok",
                           result={"status": "ok", "summary": "xong"},
                           validation={"passed": True})
        j = self.st.job(jid)
        self.assertEqual(j.status, "ok")
        self.assertTrue(j.finished)
        self.assertEqual(j.result["summary"], "xong")
        self.assertTrue(j.validation["passed"])


class TestThuLaiCoChan(_Nen):
    def test_tra_ve_hang_doi_toi_da_max_attempts(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"},
                               max_attempts=2)
        self.assertTrue(self.st.claim(jid, "AG01"))
        self.assertTrue(self.st.tra_ve_hang_doi(jid, ly_do="hỏng"))
        self.assertTrue(self.st.claim(jid, "AG02"))
        # Da dung 2/2 luot -> khong duoc tra ve hang doi nua.
        self.assertFalse(self.st.tra_ve_hang_doi(jid, ly_do="hỏng"),
                         "vòng thử lại phải CHẶN, không được vô hạn")

    def test_tried_giu_lich_su_de_doi_worker(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"},
                               max_attempts=3)
        self.st.claim(jid, "AG01")
        self.st.tra_ve_hang_doi(jid, ly_do="hỏng")
        self.st.claim(jid, "AG01")
        self.st.tra_ve_hang_doi(jid, ly_do="hỏng")
        self.st.claim(jid, "CODEX01")
        self.assertEqual(self.st.job(jid).tried, ["AG01", "AG01", "CODEX01"])

    def test_dat_max_attempts_la_hanh_dong_rieng(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"},
                               max_attempts=1)
        self.st.claim(jid, "AG01")
        self.assertFalse(self.st.tra_ve_hang_doi(jid, ly_do="hết lượt"))
        self.st.dat_max_attempts(jid, 3)
        self.assertTrue(self.st.tra_ve_hang_doi(jid, ly_do="retry thủ công"))


class TestHuy(_Nen):
    def test_huy_viec_dang_cho(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.assertTrue(self.st.huy_neu_dang_cho(jid))
        self.assertEqual(self.st.job(jid).status, "cancelled")

    def test_khong_huy_duoc_viec_dang_chay_bang_hang_doi(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.st.claim(jid, "AG01")
        self.assertFalse(self.st.huy_neu_dang_cho(jid))
        self.st.yeu_cau_huy(jid)
        self.assertTrue(self.st.job(jid).cancel_requested)


class TestBenQuaTienTrinh(_Nen):
    def test_mo_lai_so_doc_duoc_trang_thai_cu(self):
        rid = self.st.tao_run(base_sha="x")
        jid = self.st.them_job(run_id=rid, node_id="A", node={"id": "A"})
        self.st.claim(jid, "AG01")
        self.st.close()
        # Mot "tien trinh" khac mo lai cung tep — day la ca y nghia cua
        # "ben qua phien Claude".
        st2 = PoolStore(root=self.root)
        j = st2.job(jid)
        self.assertEqual(j.worker_id, "AG01")
        self.assertEqual(j.status, "running")
        self.assertEqual(st2.run_gan_nhat(), rid)
        st2.close()

    def test_ghi_worker_cap_nhat_chu_khong_nhan_doi(self):
        self.st.ghi_worker({"worker_id": "AG01", "state": "READY"})
        self.st.ghi_worker({"worker_id": "AG01", "state": "BUSY",
                            "active_job": "job-1"})
        ws = self.st.workers()
        self.assertEqual(len(ws), 1)
        self.assertEqual(ws[0]["state"], "BUSY")
        self.assertEqual(ws[0]["active_job"], "job-1")


if __name__ == "__main__":
    unittest.main()
