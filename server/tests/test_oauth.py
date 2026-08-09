"""
Dang nhap bang Google/Facebook.

HAI DIEU BO TEST NAY BAO VE, va ca hai deu hong mot cach IM LANG neu sai:

  1. **Khong co he thong phien thu hai.** Ket qua cua OAuth phai la DUNG hinh
     dang `{token, profile}` ma `/api/auth/login` da tra ve suot tu dau. Neu
     lech, frontend se can hai duong xu ly phien, va duong it dung hon se muc
     dan.

  2. **Khong co open redirect.** `/api/auth/oauth/{provider}` nhan `next` truc
     tiep tu URL roi NHUNG no vao dia chi ma Appwrite se dieu huong trinh duyet
     toi. Kiem o trinh duyet la khong du — trinh duyet khong phai hang rao.
     Open redirect o duong dang nhap dac biet nguy hiem: nguoi dung go mat
     khau o dung ten mien that roi bi day sang cho khac.

Chay hoan toan offline: dung `MockIdentityAdapter`, khong goi Appwrite.
"""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import AuthError, MockIdentityAdapter


def client() -> TestClient:
    return TestClient(server_main.app)


class DungIdentityGia(unittest.TestCase):
    """Cai `MockIdentityAdapter` cho MOT bai test, tu go ra khi xong."""

    def setUp(self) -> None:
        self.identity = MockIdentityAdapter()
        cu = server_main.identity
        server_main.identity = self.identity

        def hoan_nguyen() -> None:
            server_main.identity = cu

        self.addCleanup(hoan_nguyen)
        self.c = client()


# ---------------------------------------------------------------- bat dau


class BatDauOAuth(DungIdentityGia):

    def test_google_tra_ve_307_kem_Location(self) -> None:
        r = self.c.get("/api/auth/oauth/google?next=/write", follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertTrue(r.headers.get("location"))

    def test_facebook_cung_vay(self) -> None:
        r = self.c.get("/api/auth/oauth/facebook", follow_redirects=False)
        self.assertEqual(r.status_code, 307)

    def test_provider_la_bi_tu_choi(self) -> None:
        """
        Ten provider di THANG vao URL cua Appwrite. Nhan bat ky chuoi nao la mo
        mot open redirect thu hai.
        """
        for xau in ("evil", "google2", "../../evil", "GOOGLEX"):
            r = self.c.get(f"/api/auth/oauth/{xau}", follow_redirects=False)
            self.assertEqual(r.status_code, 404, xau)

    def test_ten_provider_khong_phan_biet_hoa_thuong(self) -> None:
        r = self.c.get("/api/auth/oauth/Google", follow_redirects=False)
        self.assertEqual(r.status_code, 307)

    def _next_trong_success(self, next_raw: str) -> str:
        r = self.c.get(f"/api/auth/oauth/google?next={next_raw}",
                       follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        success = parse_qs(urlparse(r.headers["location"]).query)["success"][0]
        return parse_qs(urlparse(success).query)["next"][0]

    def test_next_noi_bo_duoc_giu(self) -> None:
        self.assertEqual(self._next_trong_success("/write"), "/write")
        self.assertEqual(self._next_trong_success("/library"), "/library")

    def test_next_ra_ngoai_mien_bi_bo(self) -> None:
        """Moi dang duoi day tung la mot cach that de vuot qua bo loc yeu."""
        for doc_hai in (
            "https://ke-xau.tld",
            "http://ke-xau.tld",
            "//ke-xau.tld",              # protocol-relative
            "/\\ke-xau.tld",             # mot so trinh duyet doi \ thanh /
            "javascript:alert(1)",
            "write",                      # thieu dau `/`
        ):
            self.assertEqual(self._next_trong_success(doc_hai), "/", doc_hai)

    def test_next_tro_ve_chinh_trang_dang_nhap_bi_bo(self) -> None:
        """Dang nhap xong lai ve trang dang nhap la mot vong lap."""
        self.assertEqual(self._next_trong_success("/login"), "/")

    def test_URL_dich_co_ca_success_lan_failure(self) -> None:
        r = self.c.get("/api/auth/oauth/google", follow_redirects=False)
        q = parse_qs(urlparse(r.headers["location"]).query)
        self.assertIn("success", q)
        self.assertIn("failure", q)
        self.assertIn("/auth/callback", q["success"][0])
        self.assertIn("/login", q["failure"][0])

    def test_khong_lo_API_key_ra_URL(self) -> None:
        r = self.c.get("/api/auth/oauth/google", follow_redirects=False)
        loc = r.headers["location"]
        for cam in ("api_key", "apiKey", "X-Appwrite-Key", "secret"):
            self.assertNotIn(cam, loc)


# -------------------------------------------------------------- doi token


class DoiToken(DungIdentityGia):

    def _mot_nguoi_dung(self) -> str:
        p = self.identity.register("ai_do@vi-du.test", "matkhaudai123", "Ai Đó")
        return p.user_id

    def test_cap_hop_le_tra_ve_dung_hinh_dang_nhu_dang_nhap_thuong(self) -> None:
        uid = self._mot_nguoi_dung()
        self.identity.seed_oauth_token(uid, "bi-mat-1")

        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": uid, "secret": "bi-mat-1"})
        self.assertEqual(r.status_code, 200)
        body = r.json()

        # So DUNG BANG hinh dang cua `/api/auth/login`, khong phai "co chua".
        self.assertEqual(set(body), {"token", "profile"})
        thuong = self.c.post("/api/auth/login",
                             json={"email": "ai_do@vi-du.test",
                                   "password": "matkhaudai123"})
        self.assertEqual(set(body), set(thuong.json()))
        self.assertEqual(set(body["profile"]), set(thuong.json()["profile"]))

    def test_token_do_dung_duoc_that(self) -> None:
        uid = self._mot_nguoi_dung()
        self.identity.seed_oauth_token(uid, "bi-mat-2")
        token = self.c.post("/api/auth/oauth/exchange",
                            json={"user_id": uid, "secret": "bi-mat-2"}
                            ).json()["token"]

        me = self.c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["profile"]["user_id"], uid)

    def test_thieu_tham_so_bi_tu_choi(self) -> None:
        r = self.c.post("/api/auth/oauth/exchange", json={})
        self.assertEqual(r.status_code, 422)
        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": "u1", "secret": ""})
        self.assertEqual(r.status_code, 422)

    def test_cap_sai_bi_tu_choi_401(self) -> None:
        uid = self._mot_nguoi_dung()
        self.identity.seed_oauth_token(uid, "bi-mat-3")
        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": uid, "secret": "sai"})
        self.assertEqual(r.status_code, 401)

    def test_secret_cua_nguoi_khac_bi_tu_choi(self) -> None:
        """Cap phai khop CA HAI ve — khong chi secret dung la du."""
        uid = self._mot_nguoi_dung()
        self.identity.seed_oauth_token(uid, "bi-mat-4")
        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": "nguoi-khac", "secret": "bi-mat-4"})
        self.assertEqual(r.status_code, 401)

    def test_cap_chi_dung_DUOC_MOT_LAN(self) -> None:
        """
        Mot secret lot ra ngoai (lich su trinh duyet, log proxy) khong duoc
        con doi duoc thanh phien lan nua.
        """
        uid = self._mot_nguoi_dung()
        self.identity.seed_oauth_token(uid, "bi-mat-5")
        body = {"user_id": uid, "secret": "bi-mat-5"}
        self.assertEqual(self.c.post("/api/auth/oauth/exchange", json=body).status_code, 200)
        self.assertEqual(self.c.post("/api/auth/oauth/exchange", json=body).status_code, 401)

    def test_thong_bao_loi_KHONG_chua_secret(self) -> None:
        uid = self._mot_nguoi_dung()
        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": uid, "secret": "bi-mat-rat-de-nhan-ra"})
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("bi-mat-rat-de-nhan-ra", r.text)
        self.assertNotIn(uid, r.text)


# ------------------------------------------------------- lap cho ho so


class LapChoHoSo(DungIdentityGia):
    """
    Nguoi dang nhap bang Google KHONG di qua `/api/auth/register`, nen ho
    khong co ban ghi ho so nao. Nhung ho so DA CO thi khong duoc dung toi.
    """

    def test_nguoi_dung_moi_duoc_tao_ho_so_mac_dinh(self) -> None:
        # Chua tung dang ky: chi co danh tinh, chua co ho so.
        self.identity._profiles.clear()
        self.identity._tokens["tok-moi"] = "u-moi"
        self.identity.seed_oauth_token("u-moi", "bi-mat")

        from server.domain import Profile, Tier

        self.identity._profiles["u-moi"] = Profile(
            user_id="u-moi", email="moi@vi-du.test", display_name="Mới")
        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": "u-moi", "secret": "bi-mat"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["tier"], Tier.FREE.value)

    def test_ho_so_da_co_duoc_GIU_NGUYEN(self) -> None:
        """
        Nguoi dung doi ten hien thi trong Fanfic roi mot thang sau dang nhap
        bang Google khong duoc bi Google dat lai ten ho.
        """
        from server.domain import Profile

        goc = Profile(user_id="u-cu", email="cu@vi-du.test",
                      display_name="Tên Tôi Tự Đặt")
        self.identity._profiles["u-cu"] = goc
        self.identity._tokens["tok-cu"] = "u-cu"
        self.identity.seed_oauth_token("u-cu", "bi-mat-cu")

        r = self.c.post("/api/auth/oauth/exchange",
                        json={"user_id": "u-cu", "secret": "bi-mat-cu"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["profile"]["display_name"], "Tên Tôi Tự Đặt")

    def test_ensure_profile_la_tim_hoac_tao_chu_khong_ghi_de(self) -> None:
        from server.domain import Profile

        goc = Profile(user_id="u1", email="a@b.test", display_name="Giữ")
        self.identity.ensure_profile(goc)
        khac = Profile(user_id="u1", email="a@b.test", display_name="Đè")
        self.assertEqual(self.identity.ensure_profile(khac).display_name, "Giữ")


# ------------------------------------------------- khong pha duong cu


class DuongEmailKhongDoi(DungIdentityGia):

    def test_dang_ky_dang_nhap_dang_xuat_van_chay(self) -> None:
        r = self.c.post("/api/auth/register",
                        json={"email": "cu@vi-du.test", "password": "matkhaudai123",
                              "display_name": "Cũ"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(set(r.json()), {"token", "profile"})

        r = self.c.post("/api/auth/login",
                        json={"email": "cu@vi-du.test", "password": "matkhaudai123"})
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]

        self.assertEqual(
            self.c.get("/api/auth/me",
                       headers={"Authorization": f"Bearer {token}"}).status_code, 200)
        self.assertEqual(
            self.c.post("/api/auth/logout",
                        headers={"Authorization": f"Bearer {token}"}).status_code, 200)
        # Sau khi dang xuat, token het gia tri.
        self.assertEqual(
            self.c.get("/api/auth/me",
                       headers={"Authorization": f"Bearer {token}"}).status_code, 401)


class HopDongAdapter(unittest.TestCase):
    """Ban that va ban mock phai co cung be mat, neu khong test khong noi len gi."""

    def test_ca_hai_adapter_deu_co_du_ba_ham_OAuth(self) -> None:
        from server.appwrite_adapter import AppwriteIdentityAdapter

        for lop in (MockIdentityAdapter, AppwriteIdentityAdapter):
            for ten in ("oauth_start_url", "exchange_oauth_token", "ensure_profile"):
                self.assertTrue(callable(getattr(lop, ten, None)),
                                f"{lop.__name__} thiếu {ten}")

    def test_adapter_that_KHONG_chuyen_tiep_thong_diep_goc_cua_Appwrite(self) -> None:
        """
        Thong diep loi cua Appwrite co the nhac lai tham so vua gui — tuc la
        chinh cai secret — va thong diep loi thi di thang ra trinh duyet.
        """
        import inspect

        from server.appwrite_adapter import AppwriteIdentityAdapter

        nguon = inspect.getsource(AppwriteIdentityAdapter.exchange_oauth_token)
        self.assertIn("raise AuthError(", nguon)
        self.assertIn("from exc", nguon)
        # Khong duoc dung `str(exc)` de dung lai loi goc.
        self.assertNotIn("str(exc)", nguon)

    def test_khong_bao_gio_nem_AuthError_kem_secret(self) -> None:
        adapter = MockIdentityAdapter()
        with self.assertRaises(AuthError) as ctx:
            adapter.exchange_oauth_token("u1", "bi-mat-de-nhan-ra")
        self.assertNotIn("bi-mat-de-nhan-ra", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
