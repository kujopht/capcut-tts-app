"""Bai kiem cho cong dien tap khoi phuc Appwrite.

Trong tam la RANH GIOI: dien tap khong bao gio duoc tro vao production. Moi
duong lot luoi da nghi ra deu co mot bai o day — thieu scheme, chu HOA, dau
cham cuoi, ten con, va dia chi IP.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest

from scripts.ops.appwrite_restore_rehearsal import (
    HOST_CAM,
    VOLUME,
    DichCamError,
    ke_hoach,
    phan_giai_dich,
)


class TestChanProduction(unittest.TestCase):
    def test_appwrite_dev_bi_cam_du_ten_co_chu_dev(self):
        # Bay chinh: ten may co chu `dev` nhung `docs/PRODUCTION_CUTOVER.md`
        # muc 0 da do duoc rang day la toa do Appwrite PRODUCTION.
        with self.assertRaises(DichCamError):
            phan_giai_dich("https://appwrite-dev.fanfic.world/v1")

    def test_moi_host_cam_deu_bi_chan(self):
        for h in HOST_CAM:
            with self.subTest(host=h), self.assertRaises(DichCamError):
                phan_giai_dich(f"https://{h}/v1")

    def test_thieu_scheme_van_bi_chan(self):
        # Mot lan go thieu `https://` khong duoc phep bien thanh lot luoi.
        with self.assertRaises(DichCamError):
            phan_giai_dich("appwrite-dev.fanfic.world/v1")

    def test_chu_hoa_van_bi_chan(self):
        with self.assertRaises(DichCamError):
            phan_giai_dich("https://Appwrite-Dev.Fanfic.World/v1")

    def test_dau_cham_cuoi_van_bi_chan(self):
        # `host.` va `host` la cung mot dich trong DNS.
        with self.assertRaises(DichCamError):
            phan_giai_dich("https://appwrite-dev.fanfic.world./v1")

    def test_ip_production_bi_chan(self):
        with self.assertRaises(DichCamError):
            phan_giai_dich("https://35.225.209.115/v1")

    def test_ten_con_cua_vung_production_bi_chan(self):
        with self.assertRaises(DichCamError):
            phan_giai_dich("https://bat-ky.fanfic.world/v1")

    def test_endpoint_rong_bi_chan(self):
        with self.assertRaises(DichCamError):
            phan_giai_dich("")

    def test_dich_co_lap_duoc_chap_nhan(self):
        d = phan_giai_dich("https://rehearsal.example.net/v1")
        self.assertEqual(d.host, "rehearsal.example.net")

    def test_ten_gan_giong_khong_bi_chan_nham(self):
        # `fanfic.world.example.net` KHONG phai vung production; chan no se
        # la duong tinh gia lam cong tro nen phien va bi tat.
        d = phan_giai_dich("https://fanfic.world.example.net/v1")
        self.assertEqual(d.host, "fanfic.world.example.net")


class TestKeHoach(unittest.TestCase):
    def test_co_chot_chan_nham_may(self):
        kh = "\n".join(ke_hoach("20260903T163727Z", "may-thu"))
        self.assertIn("fanfic-appwrite-temp", kh)
        self.assertIn("exit 9", kh)

    @unittest.skipUnless(shutil.which("bash"), "can bash de chay that")
    def test_chot_chan_may_CHAY_THAT_va_dung_chieu(self):
        # Bai o tren chi kiem rang CHUOI `fanfic-appwrite-temp` co mat. Mot
        # chot bi DAO CHIEU van qua duoc bai do — no se chay tiep tren
        # production va dung lai tren may dien tap, dung nguoc hoan toan.
        # Nen o day ta CHAY that dong lenh do voi hai hostname va doi dung
        # ma thoat. Kiem hanh vi, khong kiem van ban.
        dong = next(d for d in ke_hoach("s", "may-thu")
                    if "fanfic-appwrite-temp" in d and "exit 9" in d)

        def chay(hostname: str) -> int:
            kich_ban = f'hostname() {{ echo "{hostname}"; }}\n{dong}\nexit 0\n'
            return subprocess.run(["bash", "-c", kich_ban],
                                  capture_output=True, text=True).returncode

        self.assertEqual(chay("fanfic-appwrite-temp"), 9,
                         "chot PHAI dung lai tren may production")
        self.assertEqual(chay("may-dien-tap"), 0,
                         "chot KHONG duoc chan may dien tap")

    def test_moi_volume_deu_duoc_nap(self):
        kh = "\n".join(ke_hoach("20260903T163727Z", "may-thu"))
        for vol in VOLUME.values():
            self.assertIn(f"docker volume create {vol}", kh)

    def test_khong_co_lenh_xoa(self):
        # Ke hoach chi duoc THEM. Mot `docker volume rm` lot vao day se chay
        # tren mot may co du lieu that.
        kh = "\n".join(ke_hoach("20260903T163727Z", "may-thu"))
        for nguy in ("volume rm", "volume prune", "system prune",
                     "compose down -v", "rm -rf"):
            self.assertNotIn(nguy, kh)

    def test_doi_phien_ban_chu_khong_chi_doi_cong(self):
        # `curl localhost` tra 200 khi traefik len, RAT LAU truoc khi
        # Appwrite san sang. Phai doi `/v1/health/version`.
        kh = "\n".join(ke_hoach("20260903T163727Z", "may-thu"))
        self.assertIn("/v1/health/version", kh)

    def test_co_kiem_mongod_mo_duoc_kho(self):
        kh = "\n".join(ke_hoach("20260903T163727Z", "may-thu"))
        self.assertIn("listDatabases", kh)

    def test_thu_muc_tuy_chon_duoc_ton_trong(self):
        kh = "\n".join(ke_hoach("s", "may-thu", "/srv/dientap"))
        self.assertIn("mkdir -p /srv/dientap", kh)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
