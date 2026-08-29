"""
Overnight P14 (Story Harvester V3 Phase 18 prep) — kiem chung KHA NANG
PHAN LOAI cua `scripts/story_harvester_production_certification.py`: bon
loai that bai (STALE_DEPLOYMENT/AUTH_FAILURE/SCRAPER_BUG/NETWORK_FAILURE)
phai duoc phan biet DUNG, khong gop chung — day la yeu cau CHINH cua kich
ban nay, kiem thu TRUC TIEP thay vi chi tin code doc qua.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

_THU_MUC_GOC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DUONG_DAN = os.path.join(_THU_MUC_GOC, "scripts", "story_harvester_production_certification.py")


def _nap_module():
    spec = importlib.util.spec_from_file_location("_cert_qa", _DUONG_DAN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NetworkFailureClassificationTest(unittest.TestCase):
    def test_khong_ket_noi_duoc_bi_gan_nhan_NETWORK_FAILURE(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return -1, {"loi": "ConnectionRefusedError"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            cert.buoc_suc_khoe_va_sha("https://khong-that.invalid", None)

        loai = {k["loai"] for k in cert.KET_QUA if not k["dat"]}
        self.assertIn(cert.NETWORK_FAILURE, loai)
        self.assertNotIn(cert.SCRAPER_BUG, loai)
        self.assertNotIn(cert.AUTH_FAILURE, loai)


class StaleDeploymentClassificationTest(unittest.TestCase):
    def test_route_404_bi_gan_nhan_STALE_DEPLOYMENT(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return 404, {"detail": "Not Found"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            cert.buoc_route_ton_tai("https://khong-that.invalid", "tok")

        loai = {k["loai"] for k in cert.KET_QUA if not k["dat"]}
        self.assertEqual(loai, {cert.STALE_DEPLOYMENT})

    def test_sha_khong_khop_bi_gan_nhan_STALE_DEPLOYMENT(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return 200, {"data_backend": "appwrite", "commit_sha": "aaaaaaaaaaaaaaaa"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            cert.buoc_suc_khoe_va_sha("https://khong-that.invalid", "bbbbbbbbbbbbbbbb")

        loai = {k["loai"] for k in cert.KET_QUA if not k["dat"]}
        self.assertEqual(loai, {cert.STALE_DEPLOYMENT})


class StaleDeploymentDungSomTest(unittest.TestCase):
    """`buoc_suc_khoe_va_sha` PHAI tra ve False khi SHA khong dat.

    Cac test o tren chi kiem tra NHAN (`loai`) trong `KET_QUA` — chung van
    xanh ca khi ham tra ve True, nen chung KHONG bao ve duoc hanh vi dung
    som. Do chinh la lo hong that: ban dau ham luon `return True`, nen
    `main()` bo qua nhanh dung som cua chinh no va di tiep toi buoc quet
    nho — tuc la chung nhan VAN cham that vao san xuat tren mot ban deploy
    da biet la cu. Verdict cuoi cung van FAIL (main() tong hop tu KET_QUA),
    nen day khong phai PASS gia, nhung no lam viec thua va gay hieu nham.

    Hai test duoi day la thu DUY NHAT se do neu ai do doi `return sha_ok`
    nguoc lai thanh `return True`.
    """

    def test_thieu_sha_tra_ve_False_de_main_dung_som(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            # Dung hinh dang THAT dang chay tren san xuat hom nay: health 200,
            # kho that, nhung KHONG co truong commit_sha.
            return 200, {"data_backend": "appwrite"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            ket_qua = cert.buoc_suc_khoe_va_sha("https://khong-that.invalid", "a" * 40)

        self.assertFalse(
            ket_qua,
            "thieu commit_sha phai tra ve False de main() DUNG SOM, "
            "khong di tiep sang buoc quet nho tren ban deploy cu",
        )

    def test_sha_khong_khop_tra_ve_False_de_main_dung_som(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return 200, {"data_backend": "appwrite", "commit_sha": "a" * 40}

        with patch.object(cert, "goi", side_effect=goi_gia):
            ket_qua = cert.buoc_suc_khoe_va_sha("https://khong-that.invalid", "b" * 40)

        self.assertFalse(ket_qua, "SHA lech phai tra ve False de main() DUNG SOM")

    def test_khong_yeu_cau_sha_van_di_tiep_binh_thuong(self):
        """Khong duoc chan qua tay: khong truyen --expected-sha thi van True."""
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return 200, {"data_backend": "appwrite"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            ket_qua = cert.buoc_suc_khoe_va_sha("https://khong-that.invalid", None)

        self.assertTrue(ket_qua, "khong co --expected-sha thi khong duoc dung som")


class AuthFailureClassificationTest(unittest.TestCase):
    def test_cong_khong_doi_hoi_token_bi_gan_nhan_AUTH_FAILURE(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            # Mo phong LOI THAT SU: tra 200 du KHONG co token — cong admin
            # khong duoc bao ve dung.
            return 200, {"supported": True}

        with patch.object(cert, "goi", side_effect=goi_gia):
            cert.buoc_cong_admin_that_su_doi_hoi_token("https://khong-that.invalid")

        loai = {k["loai"] for k in cert.KET_QUA if not k["dat"]}
        self.assertEqual(loai, {cert.AUTH_FAILURE})

    def test_cong_doi_hoi_token_dung_khong_bi_bao_loi(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            return 401, {"detail": "unauthorized"}

        with patch.object(cert, "goi", side_effect=goi_gia):
            ok = cert.buoc_cong_admin_that_su_doi_hoi_token("https://khong-that.invalid")
        self.assertTrue(ok)
        self.assertTrue(all(k["dat"] for k in cert.KET_QUA))


class ScraperBugClassificationTest(unittest.TestCase):
    def test_discover_tra_du_lieu_sai_hinh_dang_bi_gan_nhan_SCRAPER_BUG(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            # HTTP 200 (route hoat dong, xac thuc qua) NHUNG du lieu SAI
            # hinh dang mong doi (thieu "supported").
            return 200, {"noi_dung_khong_lien_quan": True}

        with patch.object(cert, "goi", side_effect=goi_gia):
            cert.buoc_discover_va_dry_run("https://khong-that.invalid", "tok", "https://vidu.test/x")

        loai = {k["loai"] for k in cert.KET_QUA if not k["dat"]}
        self.assertEqual(loai, {cert.SCRAPER_BUG})


class OverallVerdictTest(unittest.TestCase):
    def test_chapter_limit_qua_5_tu_choi_truoc_khi_cham_mang(self):
        cert = _nap_module()
        with patch.object(cert, "goi") as goi_gia:
            ma = cert.main([
                "--api", "https://khong-that.invalid", "--admin-token", "tok",
                "--source-url", "https://vidu.test/x", "--chapter-limit", "50",
            ])
        self.assertEqual(ma, 2)
        goi_gia.assert_not_called()

    def test_tat_ca_dat_tra_ve_verdict_pass(self):
        cert = _nap_module()

        def goi_gia(api, method, path, payload=None, token=None, timeout=60):
            if path == "/api/health":
                return 200, {"data_backend": "appwrite"}
            if not token and "discover" in path:
                return 401, {}
            if token == "token-gia-mao-khong-hop-le":
                return 401, {}
            if path == "/api/admin/scraper/runs" and method == "GET":
                return 200, {}
            if path == "/api/admin/scraper/discover":
                return 200, {"supported": True, "run": {"estimated_total": 5}}
            if path == "/api/admin/scraper/check-mirror":
                return 200, {}
            if path == "/api/admin/scraper/runs" and method == "POST":
                return 200, {"run": {"run_id": "scr_gia_lap"}}
            if path.endswith("/drive"):
                return 200, {}
            if path == "/api/admin/scraper/runs/scr_gia_lap":
                return 200, {"run": {"status": "completed"}, "items": []}
            if path.endswith("/cancel"):
                return 200, {}
            if path.endswith("/retry"):
                return 200, {}
            if path.endswith("/check-updates"):
                return 200, {}
            return 404, {}

        with patch.object(cert, "goi", side_effect=goi_gia):
            ma = cert.main([
                "--api", "https://khong-that.invalid", "--admin-token", "tok-dung",
                "--source-url", "https://vidu.test/x",
            ])
        self.assertEqual(ma, 0, [k for k in cert.KET_QUA if not k["dat"]])


if __name__ == "__main__":
    unittest.main()
