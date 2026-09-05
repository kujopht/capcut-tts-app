"""Bai kiem cho bo dieu phoi cutover Appwrite.

Trong tam la CHAN, khong phai chay. Moi bai o day hoi cung mot cau: khi
dieu kien an toan KHONG chung minh duoc, cong co that su dung lai khong?

Khong bai nao goi mang, GCE, AWS hay Cloudflare.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from scripts.ops import appwrite_prod_cutover as pc


class _Nen(unittest.TestCase):
    """Doi trang thai sang thu muc tam de khong dung vao trang thai that."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cutover-test-"))
        self._tt = pc.TEP_TRANG_THAI
        self._nk = pc.NHAT_KY
        pc.TEP_TRANG_THAI = self.tmp / "state.json"
        pc.NHAT_KY = self.tmp / "audit.jsonl"

    def tearDown(self):
        pc.TEP_TRANG_THAI = self._tt
        pc.NHAT_KY = self._nk


def _dat_toi(pha: str, **them):
    """Danh dau MOI pha truoc `pha` la DAT voi moc thoi gian hop le."""
    for p in pc.THU_TU[:pc.THU_TU.index(pha)]:
        pc.dat_pha(p)
    if them:
        pc.ghi_trang_thai(**them)


class TestThuTuPha(_Nen):
    def test_khong_duoc_nhay_coc(self):
        # Chua preflight ma da doi restore/canary -> phai tu choi.
        for pha in ("prepare", "freeze", "final-backup", "restore", "canary",
                    "cutover", "observe", "commit"):
            with self.subTest(pha=pha), self.assertRaises(pc.CutoverRefused):
                pc.doi_pha_truoc(pha)

    def test_pha_dau_khong_can_gi_truoc(self):
        pc.doi_pha_truoc("preflight")  # khong duoc nem

    def test_pha_truoc_HONG_van_bi_chan(self):
        pc.ghi_trang_thai(**{"pha.preflight": "HONG"})
        with self.assertRaises(pc.CutoverRefused):
            pc.doi_pha_truoc("prepare")

    def test_pha_truoc_DAT_thi_di_tiep_duoc(self):
        pc.dat_pha("preflight")
        pc.doi_pha_truoc("prepare")  # khong nem

    def test_DAT_nhung_KHONG_co_moc_thoi_gian_bi_tu_choi(self):
        # Trang thai sua tay / tu ban cu: co "DAT" nhung thieu moc.
        pc.ghi_trang_thai(**{"pha.preflight": "DAT"})
        with self.assertRaises(pc.CutoverRefused):
            pc.doi_pha_truoc("prepare")

    def test_ket_qua_QUA_HAN_bi_tu_choi(self):
        # preflight cua ba ngay truoc khong noi duoc gi ve production hom nay.
        cu = datetime.now(timezone.utc) - timedelta(
            hours=pc.HAN_KET_QUA_PHA_GIO + 2)
        pc.ghi_trang_thai(**{
            "pha.preflight": "DAT",
            "pha.preflight.luc": cu.strftime("%Y-%m-%dT%H:%M:%SZ")})
        with self.assertRaises(pc.CutoverRefused) as e:
            pc.doi_pha_truoc("prepare")
        self.assertIn("han", str(e.exception))

    def test_pha_XA_hon_van_bi_chan_du_hang_xom_DAT(self):
        # Bay ma vong phan bien tim ra: chi kiem hang xom truc tiep thi mot
        # lan chay bo do co the lot. Gio kiem TOAN BO day truoc.
        pc.dat_pha("restore")            # hang xom truc tiep cua canary
        with self.assertRaises(pc.CutoverRefused):
            pc.doi_pha_truoc("canary")   # nhung preflight/prepare/... chua DAT

    def test_thu_tu_dung_nhu_thiet_ke(self):
        self.assertEqual(
            pc.THU_TU,
            ["preflight", "prepare", "freeze", "final-backup", "restore",
             "canary", "cutover", "observe", "commit"])

    def test_moi_pha_trong_THU_TU_deu_co_ham_that(self):
        # `restore` tung nam trong THU_TU ma KHONG co ham nao trong PHA —
        # quy trinh khong the chay het duong. Bai nay giu dieu do khong tai dien.
        for p in pc.THU_TU:
            self.assertIn(p, pc.PHA, f"pha '{p}' khong co ham thuc thi")


class TestPrepareTonTien(_Nen):
    def setUp(self):
        super().setUp()
        _dat_toi("prepare")

    def test_khong_co_co_dong_y_thi_tu_choi(self):
        a = argparse.Namespace(toi_dong_y_tra_tien=False, dry_run=True)
        with self.assertRaises(pc.CutoverRefused) as e:
            pc.pha_prepare(a)
        self.assertIn("tinh tien", str(e.exception).lower().replace("í", "i"))

    def test_co_co_dong_y_va_dry_run_thi_khong_goi_aws(self):
        a = argparse.Namespace(toi_dong_y_tra_tien=True, dry_run=True)
        self.assertEqual(pc.pha_prepare(a), 0)


class TestTuoiBackup(_Nen):
    def test_chua_co_anh_chup_thi_tu_choi(self):
        with self.assertRaises(pc.CutoverRefused):
            pc._tuoi_backup_phut()

    def test_anh_chup_qua_cu_thi_CHAN_cutover(self):
        cu = datetime.now(timezone.utc) - timedelta(
            minutes=pc.TUOI_BACKUP_TOI_DA_PHUT + 10)
        _dat_toi("cutover",
                 snapshot_luc=cu.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 aws_ip="203.0.113.9")
        a = argparse.Namespace(dry_run=True)
        with self.assertRaises(pc.CutoverRefused) as e:
            pc.pha_cutover(a)
        self.assertIn("final-backup", str(e.exception))

    def test_anh_chup_moi_thi_cho_qua(self):
        moi = datetime.now(timezone.utc) - timedelta(minutes=5)
        _dat_toi("cutover",
                 snapshot_luc=moi.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 aws_ip="203.0.113.9")
        # dry-run: dung truoc khi cham Cloudflare, nhung PHAI qua duoc cong tuoi
        self.assertEqual(pc.pha_cutover(argparse.Namespace(dry_run=True)), 0)


class TestGiuGCE(_Nen):
    def _san_sang(self, ngay_truoc: int):
        luc = datetime.now(timezone.utc) - timedelta(days=ngay_truoc)
        _dat_toi("commit", cutover_luc=luc.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_chua_het_thoi_gian_giu_thi_KHONG_duoc_dung_GCE(self):
        self._san_sang(pc.NGAY_GIU_GCE - 3)
        with self.assertRaises(pc.CutoverRefused) as e:
            pc.pha_commit(argparse.Namespace())
        self.assertIn("duong lui", str(e.exception))

    def test_het_thoi_gian_giu_thi_cho_phep(self):
        self._san_sang(pc.NGAY_GIU_GCE + 1)
        self.assertEqual(pc.pha_commit(argparse.Namespace()), 0)

    def test_khong_co_moc_cutover_thi_tu_choi(self):
        _dat_toi("commit")
        with self.assertRaises(pc.CutoverRefused):
            pc.pha_commit(argparse.Namespace())


class TestTieuChiRollback(_Nen):
    def test_health_khong_200_la_ly_do_rollback(self):
        with mock.patch.object(pc, "http_origin",
                               return_value={"status": 502, "body": ""}):
            self.assertTrue(pc._tieu_chi_rollback("203.0.113.9"))

    def test_sai_phien_ban_la_ly_do_rollback(self):
        with mock.patch.object(pc, "http_origin",
                               return_value={"status": 200,
                                             "body": '{"version":"1.8.0"}'}):
            ly_do = pc._tieu_chi_rollback("203.0.113.9")
            self.assertTrue(ly_do)
            self.assertIn("phien ban", ly_do[0])

    def test_dung_phien_ban_thi_khong_rollback(self):
        with mock.patch.object(
                pc, "http_origin",
                return_value={"status": 200,
                              "body": '{"version":"%s"}' % pc.APPWRITE_VERSION}):
            self.assertEqual(pc._tieu_chi_rollback("203.0.113.9"), [])


class TestHangSoDoDuoc(unittest.TestCase):
    """Cau hinh may dich phai khop so DA DO, khong duoc troi."""

    def test_khong_bao_gio_ARM(self):
        self.assertEqual(pc.AWS_ARCH, "x86_64")

    def test_du_8GiB_va_64GB(self):
        self.assertEqual(pc.AWS_INSTANCE_TYPE, "t3a.large")
        self.assertGreaterEqual(pc.AWS_VOLUME_GB, 64)
        self.assertEqual(pc.AWS_SWAP_GB, 4)

    def test_giu_GCE_it_nhat_mot_tuan(self):
        self.assertGreaterEqual(pc.NGAY_GIU_GCE, 7)

    def test_nguong_tuoi_backup_du_chat(self):
        # Mot gio la qua dai cho "ngay truoc khi chuyen".
        self.assertLessEqual(pc.TUOI_BACKUP_TOI_DA_PHUT, 60)

    def test_so_collection_khop_so_da_do(self):
        self.assertEqual(pc.SO_COLLECTION_PROD, 43)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
