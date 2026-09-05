"""Bai kiem cho cong doi soat ban backup Appwrite.

Moi bai dung mot ban backup TU DUNG bang tarfile trong bo nho — khong dong
vao ban that, khong can mang, khong can Docker.

Bai quan trong nhat la `test_ban_that_20260903_bi_bat`: no dung lai DUNG
hinh dang cua ban production 20260903T163727Z (turtle 23:36, journal 23:37,
mongod.lock 2 byte) va doi cong phai tra FAIL. Neu ai do noi long cong nay,
bai do gay truoc.
"""
from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.ops.appwrite_backup_verify import (
    CANH_BAO,
    FAIL,
    NGUON_ANH_CHUP,
    NGUON_TAR_SONG,
    THONG_TIN,
    doc_volume,
    kiem_backup,
    kiem_mariadb,
    kiem_wiredtiger,
    phan_loai,
)

#: Moc thoi gian goc cua cac bai kiem (epoch). Chon mot so co dinh de phep
#: tru mtime luon ra cung ket qua.
T0 = 1_756_900_000


def viet_tar(duong_dan: Path, tep: dict[str, tuple[bytes, int]]) -> Path:
    """Tao mot <volume>.tar.gz voi {ten: (noi_dung, mtime)}."""
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(duong_dan, "w:gz") as tf:
        for ten, (noi_dung, mtime) in tep.items():
            ti = tarfile.TarInfo(name=f"./{ten}")
            ti.size = len(noi_dung)
            ti.mtime = mtime
            tf.addfile(ti, io.BytesIO(noi_dung))
    return duong_dan


def mongo_lanh(mtime: int = T0) -> dict[str, tuple[bytes, int]]:
    """Mot ban chep MongoDB SACH: mongod da tat, turtle moi nhat THAT SU.

    Moi tep du lieu deu CU HON turtle han mot giay. Ban dau ham nay cho
    journal trung giay voi turtle — nhu vay no vua la 'ban sach' vua la mot
    ban co the RACH ma cong khong phan biet duoc, nen no che mat chinh loi
    do phan giai mot giay cua `tar`. Gio diem mu do co bai rieng ben duoi
    (`test_trung_giay_...`), con ban nen nay phai la sach khong ban cai.
    """
    return {
        "WiredTiger": (b"x" * 50, mtime - 100),
        "WiredTiger.wt": (b"x" * 4096, mtime - 1),
        "WiredTiger.turtle": (b"x" * 1496, mtime),
        "mongod.lock": (b"", mtime - 100),
        "_mdb_catalog.wt": (b"x" * 4096, mtime - 1),
        "collection-1.wt": (b"x" * 4096, mtime - 10),
        "journal/WiredTigerLog.0000000001": (b"x" * 4096, mtime - 1),
    }


class TestPhanLoai(unittest.TestCase):
    def test_keyfile_khong_bi_nham_la_kho_mongodb(self):
        # Thu tu quan trong: `mongodb-keyfile` chua chuoi `mongodb`, nen neu
        # phan loai sai no se bi doi hoi co WiredTiger.turtle va bao FAIL gia.
        self.assertEqual(
            phan_loai("appwrite_appwrite-mongodb-keyfile.tar.gz"),
            "mongodb-keyfile")
        self.assertEqual(
            phan_loai("appwrite_appwrite-mongodb.tar.gz"), "mongodb")

    def test_cac_loai_con_lai(self):
        self.assertEqual(phan_loai("appwrite_appwrite-mariadb.tar.gz"), "mariadb")
        self.assertEqual(phan_loai("appwrite_appwrite-uploads.tar.gz"), "uploads")
        self.assertEqual(phan_loai("mot-thu-la.tar.gz"), "khac")


class TestWiredTiger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wt-test-"))

    def _vol(self, tep: dict[str, tuple[bytes, int]]):
        p = viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", tep)
        return doc_volume(p)

    def test_ban_sach_thi_on_dinh(self):
        kq = kiem_wiredtiger(self._vol(mongo_lanh()))
        self.assertEqual([f.muc for f in kq], [THONG_TIN])
        self.assertEqual(kq[0].ma, "WT_ON_DINH")

    def test_mongod_dang_chay_bi_bat(self):
        tep = mongo_lanh()
        tep["mongod.lock"] = (b"1\n", T0 - 100)  # pid -> dang chay
        ma = {f.ma for f in kiem_wiredtiger(self._vol(tep))}
        self.assertIn("WT_MONGOD_DANG_CHAY", ma)

    def test_journal_moi_hon_turtle_bi_bat(self):
        tep = mongo_lanh()
        tep["journal/WiredTigerLog.0000000001"] = (b"x" * 4096, T0 + 44)
        kq = kiem_wiredtiger(self._vol(tep))
        ma = {f.ma for f in kq}
        self.assertIn("WT_SAO_CHEP_RACH", ma)
        rach = next(f for f in kq if f.ma == "WT_SAO_CHEP_RACH")
        self.assertEqual(rach.muc, FAIL)
        self.assertIn("+44s", rach.thong_diep)

    def test_trung_giay_voi_turtle_thi_phai_canh_bao(self):
        # Diem mu co that: `tar` chi luu mtime tron GIAY. Mot journal ghi
        # 0,8 giay SAU turtle mang dung con so giay do, nen phep so `>`
        # khong thay. Cong khong duoc IM LANG bao PASS o day.
        tep = mongo_lanh()
        tep["journal/WiredTigerLog.0000000001"] = (b"x" * 4096, T0)
        kq = kiem_wiredtiger(self._vol(tep))
        ma = {f.ma for f in kq}
        self.assertIn("WT_CUNG_GIAY", ma)
        cg = next(f for f in kq if f.ma == "WT_CUNG_GIAY")
        self.assertEqual(cg.muc, CANH_BAO)

    def test_thieu_mongod_lock_la_FAIL(self):
        # Khong co `mongod.lock` = khong co bang chung mongod da dung han.
        # Truoc day duong nay am tham di qua cong: `.get(WT_LOCK, 0) > 0`
        # coi tep VANG MAT giong het tep RONG.
        tep = mongo_lanh()
        del tep["mongod.lock"]
        kq = kiem_wiredtiger(self._vol(tep))
        ma = {f.ma for f in kq}
        self.assertIn("WT_KHONG_CO_LOCK", ma)
        self.assertTrue(any(f.muc == FAIL for f in kq))
        self.assertNotIn("WT_ON_DINH", ma)

    def test_thieu_turtle_la_FAIL(self):
        tep = mongo_lanh()
        del tep["WiredTiger.turtle"]
        kq = kiem_wiredtiger(self._vol(tep))
        self.assertEqual([f.ma for f in kq], ["WT_KHONG_CO_TURTLE"])
        self.assertEqual(kq[0].muc, FAIL)

    def test_diagnostic_data_khong_gay_bao_dong_gia(self):
        # `diagnostic.data` va `_tmp` duoc ghi lien tuc va se LUON moi hon
        # turtle. Neu tinh chung vao, moi ban backup deu FAIL — cong tro nen
        # vo dung vi keu qua nhieu.
        tep = mongo_lanh()
        tep["diagnostic.data/metrics.2026-09-03"] = (b"x" * 4096, T0 + 600)
        tep["_tmp/spilldb/WiredTiger.turtle"] = (b"x" * 100, T0 + 600)
        kq = kiem_wiredtiger(self._vol(tep))
        self.assertEqual([f.ma for f in kq], ["WT_ON_DINH"])

    def test_ban_that_20260903_bi_bat(self):
        # Dung lai DUNG hinh dang cua ban production 20260903T163727Z.
        # Neu ai do noi long cong, bai nay gay truoc.
        tep = {
            "WiredTiger": (b"x" * 50, T0 - 1_000_000),
            "WiredTiger.lock": (b"x" * 21, T0 - 1_000_000),
            "WiredTiger.wt": (b"x" * 6_778_880, T0),
            "WiredTiger.turtle": (b"x" * 1496, T0),
            "WiredTigerHS.wt": (b"x" * 86016, T0),
            "mongod.lock": (b"1\n", T0 - 900_000),
            "_mdb_catalog.wt": (b"x" * 184_320, T0 - 100_000),
            "collection-fa20def2.wt": (b"x" * 4096, T0),
            "journal/WiredTigerLog.0000000012": (b"x" * 4096, T0 + 44),
        }
        kq = kiem_wiredtiger(self._vol(tep))
        ma = {f.ma for f in kq}
        self.assertIn("WT_MONGOD_DANG_CHAY", ma)
        self.assertIn("WT_SAO_CHEP_RACH", ma)
        self.assertTrue(any(f.muc == FAIL for f in kq))


class TestMariaDB(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="maria-test-"))

    def _vol(self, tep):
        p = viet_tar(self.tmp / "appwrite_appwrite-mariadb.tar.gz", tep)
        return doc_volume(p)

    def test_chi_co_db_opt_la_khong_co_bang(self):
        # Hinh dang that tren VM: `appwrite/db.opt` va khong gi khac.
        v = self._vol({
            "ibdata1": (b"x" * 4096, T0),
            "appwrite/db.opt": (b"x" * 67, T0),
        })
        ma = {f.ma for f in kiem_mariadb(v)}
        self.assertIn("MARIADB_KHONG_CO_BANG", ma)

    def test_co_bang_that_thi_khong_bao(self):
        v = self._vol({
            "appwrite/db.opt": (b"x" * 67, T0),
            "appwrite/_1_novels.ibd": (b"x" * 4096, T0),
        })
        ma = {f.ma for f in kiem_mariadb(v)}
        self.assertNotIn("MARIADB_KHONG_CO_BANG", ma)

    def test_pid_con_lai_la_FAIL(self):
        v = self._vol({
            "appwrite/db.opt": (b"x" * 67, T0),
            "appwrite/_1_novels.ibd": (b"x" * 4096, T0),
            "mariadb.pid": (b"1\n", T0),
        })
        kq = kiem_mariadb(v)
        self.assertIn("MARIADB_DANG_CHAY", {f.ma for f in kq})
        self.assertTrue(any(f.muc == FAIL for f in kq))


class TestKiemBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backup-test-"))

    def test_thu_muc_rong_la_FAIL(self):
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["ket_luan"], "FAIL")
        self.assertEqual(kq["phat_hien"][0]["ma"], "KHONG_CO_VOLUME")

    def test_ban_tot_la_PASS(self):
        viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", mongo_lanh())
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["ket_luan"], "PASS")
        self.assertEqual(kq["kho_song"], ["mongodb"])

    def test_ban_rach_la_FAIL(self):
        tep = mongo_lanh()
        tep["journal/WiredTigerLog.0000000001"] = (b"x" * 4096, T0 + 44)
        viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", tep)
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["ket_luan"], "FAIL")

    def test_volume_rong_chi_la_canh_bao(self):
        # `uploads` rong la DUNG THIET KE o kho nay: tep nhi phan nam o R2,
        # khong o Appwrite Storage. Nen no khong duoc chan PASS.
        viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", mongo_lanh())
        viet_tar(self.tmp / "appwrite_appwrite-uploads.tar.gz", {})
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["ket_luan"], "PASS")
        rong = [f for f in kq["phat_hien"] if f["ma"] == "VOLUME_RONG"]
        self.assertEqual(len(rong), 1)
        self.assertEqual(rong[0]["muc"], CANH_BAO)

    def test_khong_co_kho_song_la_FAIL(self):
        # Chi co volume phu, khong co kho du lieu nao -> khong doi soat duoc.
        viet_tar(self.tmp / "appwrite_appwrite-config.tar.gz",
                 {"config.json": (b"{}", T0)})
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["ket_luan"], "FAIL")
        self.assertIn("KHONG_XAC_DINH_DUOC_KHO_SONG",
                      {f["ma"] for f in kq["phat_hien"]})

    def test_mariadb_rong_khong_duoc_tinh_la_kho_song(self):
        # Bay that: neu tinh mariadb (khong co bang) la kho song, cong se
        # bao PASS cho mot ban KHONG he chua du lieu nguoi dung.
        viet_tar(self.tmp / "appwrite_appwrite-mariadb.tar.gz", {
            "ibdata1": (b"x" * 4096, T0),
            "appwrite/db.opt": (b"x" * 67, T0),
        })
        kq = kiem_backup(self.tmp)
        self.assertEqual(kq["kho_song"], [])
        self.assertEqual(kq["ket_luan"], "FAIL")


class TestNguonAnhChup(unittest.TestCase):
    """Cung mot hinh dang tep, hai ket luan — vi CACH CHEP khac nhau.

    Day la bai hoc dat nhat cua ca dot: ban `tar` RACH (20260903T163727Z) va
    ban trich tu ANH CHUP KHOI (20260905) co be ngoai GIONG HET NHAU. Neu
    cong khong biet `nguon`, no phai chon mot trong hai cai sai: hoac cho
    ban rach di qua, hoac chan ban anh chup hoan toan tot.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nguon-test-"))

    def _hinh_dang_that(self):
        # Do that tu ca hai ban: lock 2 byte, journal moi hon turtle ~60s.
        tep = mongo_lanh()
        tep["mongod.lock"] = (b"1\n", T0 - 900_000)
        tep["journal/WiredTigerLog.0000000013"] = (b"x" * 4096, T0 + 60)
        return tep

    def _vol(self, tep):
        p = viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", tep)
        return doc_volume(p)

    def test_cung_hinh_dang_tar_song_thi_FAIL(self):
        kq = kiem_wiredtiger(self._vol(self._hinh_dang_that()), NGUON_TAR_SONG)
        ma = {f.ma for f in kq}
        self.assertIn("WT_MONGOD_DANG_CHAY", ma)
        self.assertIn("WT_SAO_CHEP_RACH", ma)
        self.assertTrue(any(f.muc == FAIL for f in kq))

    def test_cung_hinh_dang_anh_chup_thi_KHONG_FAIL(self):
        kq = kiem_wiredtiger(self._vol(self._hinh_dang_that()), NGUON_ANH_CHUP)
        ma = {f.ma for f in kq}
        self.assertNotIn("WT_MONGOD_DANG_CHAY", ma)
        self.assertNotIn("WT_SAO_CHEP_RACH", ma)
        self.assertIn("WT_ANH_CHUP_MONGOD_DANG_CHAY", ma)
        self.assertIn("WT_ANH_CHUP_JOURNAL_DI_TRUOC", ma)
        self.assertFalse([f.ma for f in kq if f.muc == FAIL])

    def test_anh_chup_thieu_journal_la_FAIL(self):
        # Voi anh chup, journal la thu DUY NHAT bit lai khoang cach tu
        # checkpoint cuoi toi thoi diem chup. Thieu no la mat du lieu.
        tep = self._hinh_dang_that()
        for k in [t for t in tep if t.startswith("journal/")]:
            del tep[k]
        kq = kiem_wiredtiger(self._vol(tep), NGUON_ANH_CHUP)
        self.assertIn("WT_ANH_CHUP_THIEU_JOURNAL", {f.ma for f in kq})
        self.assertTrue(any(f.muc == FAIL for f in kq))

    def test_tar_song_thieu_journal_khong_bi_bat_nham(self):
        # Ban tar cua mot mongod DA TAT SACH co the khong con journal, va do
        # khong phai loi. Chi anh chup moi bat buoc phai co.
        tep = mongo_lanh()
        for k in [t for t in tep if t.startswith("journal/")]:
            del tep[k]
        kq = kiem_wiredtiger(self._vol(tep), NGUON_TAR_SONG)
        self.assertNotIn("WT_ANH_CHUP_THIEU_JOURNAL", {f.ma for f in kq})


    def test_ly_do_on_dinh_phai_khop_nguon(self):
        # Cong in ly do SAI thi ket luan dung cung khong con dang tin.
        # Duong anh chup KHONG duoc noi "mongod.lock rong" khi no 2 byte.
        kq = kiem_wiredtiger(self._vol(self._hinh_dang_that()), NGUON_ANH_CHUP)
        od = next(f for f in kq if f.ma == "WT_ON_DINH")
        self.assertNotIn("rong", od.thong_diep)
        self.assertIn("MOT thoi diem", od.thong_diep)

    def test_ly_do_on_dinh_duong_tar_van_noi_ve_lock(self):
        kq = kiem_wiredtiger(self._vol(mongo_lanh()), NGUON_TAR_SONG)
        od = next(f for f in kq if f.ma == "WT_ON_DINH")
        self.assertIn("mongod.lock rong", od.thong_diep)

    def test_nguon_sai_bi_tu_choi(self):
        with self.assertRaises(ValueError):
            kiem_backup(self.tmp, "khong_ton_tai")


class TestThieuVolume(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thieu-test-"))

    def test_backup_thieu_volume_bi_bao(self):
        # `backup.sh` cu lay 9 volume trong khi stack that co 14. Khong tep
        # nao hong, khong sha256 nao lech — kho chi bien mat.
        viet_tar(self.tmp / "appwrite_appwrite-mongodb.tar.gz", mongo_lanh())
        kq = kiem_backup(self.tmp)
        thieu = [f for f in kq["phat_hien"] if f["ma"] == "THIEU_VOLUME"]
        self.assertEqual(len(thieu), 1)
        self.assertEqual(thieu[0]["muc"], CANH_BAO)
        for v in ("appwrite-builds", "appwrite-cache", "appwrite-sites"):
            self.assertIn(v, thieu[0]["thong_diep"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
