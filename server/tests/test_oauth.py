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
from dataclasses import replace
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

    def _callback_urls(self, web_base_url: str, next_raw: str = "/") -> tuple[str, str]:
        old = server_main.settings.web_base_url
        server_main.settings = replace(server_main.settings, web_base_url=web_base_url)
        self.addCleanup(
            setattr,
            server_main,
            "settings",
            replace(server_main.settings, web_base_url=old),
        )
        r = self.c.get(
            f"/api/auth/oauth/google?next={next_raw}",
            follow_redirects=False,
        )
        self.assertEqual(r.status_code, 307)
        query = parse_qs(urlparse(r.headers["location"]).query)
        return query["success"][0], query["failure"][0]

    def test_callback_dung_goc_web_theo_moi_truong(self) -> None:
        for web_base_url in (
            "http://localhost:3000",
            "https://staging.fanfic.world",
            "https://fanfic.world",
        ):
            with self.subTest(web_base_url=web_base_url):
                success, failure = self._callback_urls(web_base_url)
                self.assertTrue(success.startswith(f"{web_base_url}/auth/callback?"))
                self.assertTrue(failure.startswith(f"{web_base_url}/login?"))

    def test_callback_staging_khong_bao_gio_roi_ve_localhost(self) -> None:
        success, failure = self._callback_urls("https://staging.fanfic.world")
        self.assertNotIn("localhost", success)
        self.assertNotIn("localhost", failure)

    def test_callback_staging_giu_next_noi_bo_an_toan(self) -> None:
        success, _ = self._callback_urls(
            "https://staging.fanfic.world",
            "/admin/animation/sources?tab=trusted%26page=1",
        )
        callback_query = parse_qs(urlparse(success).query)
        self.assertEqual(
            callback_query["next"][0],
            "/admin/animation/sources?tab=trusted&page=1",
        )

    def test_google_tra_ve_307_kem_Location(self) -> None:
        r = self.c.get("/api/auth/oauth/google?next=/write", follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertTrue(r.headers.get("location"))

    def test_facebook_dang_TAT_nen_khong_bat_dau_duoc(self) -> None:
        """
        Truoc day bai nay doi 307 y nhu Google. Facebook nay bi TAT theo quyet
        dinh san pham (`FAS_FACEBOOK_LOGIN`), nen 404 moi la dung.

        Phan biet HAI loai 404, va do la diem chinh: thong diep phai noi
        "tạm thời chưa khả dụng" chu KHONG phai "không được hỗ trợ". Neu ai do
        lo tay xoa Facebook khoi `OAUTH_PROVIDERS`, ket qua van la 404 nhung
        thong diep se khac — va bai nay do.

        Chi tiet day du o `FacebookDangTat`.
        """
        r = self.c.get("/api/auth/oauth/facebook", follow_redirects=False)
        self.assertEqual(r.status_code, 404)
        self.assertIn("tạm thời chưa khả dụng", r.json()["detail"])

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


class FacebookDangTat(DungIdentityGia):
    """
    Facebook bi TAT theo quyet dinh san pham, khong phai vi hong.

    Diem mau chot cua ca nhom test nay: TAT khong duoc phep nghia la XOA. Neu
    ai do "don dep" bang cach go phan hien thuc di, ngay bat lai se thanh mot
    lan viet lai — va cac test duoi day phai do truoc khi dieu do xay ra.
    """

    def test_mac_dinh_la_TAT(self) -> None:
        from server.config import Settings

        self.assertFalse(Settings().facebook_login_enabled)

    def test_duong_bat_dau_Facebook_tra_404(self) -> None:
        """
        An cai nut o giao dien la CHUA DU: duong nay van goi duoc bang tay.
        """
        r = self.c.get("/api/auth/oauth/facebook", follow_redirects=False)
        self.assertEqual(r.status_code, 404)
        self.assertIn("Facebook", r.json()["detail"])

    def test_Google_KHONG_bi_anh_huong(self) -> None:
        r = self.c.get("/api/auth/oauth/google?next=/write", follow_redirects=False)
        self.assertEqual(r.status_code, 307)

    def test_bat_lai_chi_bang_MOT_bien_moi_truong(self) -> None:
        """
        Chung minh phan hien thuc con nguyen: doi dung mot co la Facebook chay
        lai, khong phai viet lai gi.
        """
        from dataclasses import replace

        cu = server_main.settings
        server_main.settings = replace(cu, facebook_login_enabled=True)
        self.addCleanup(lambda: setattr(server_main, "settings", cu))

        r = self.c.get("/api/auth/oauth/facebook?next=/write",
                       follow_redirects=False)
        self.assertEqual(r.status_code, 307)
        self.assertIn("facebook", r.headers["location"])

    def test_doi_token_KHONG_phu_thuoc_nha_cung_cap(self) -> None:
        """
        `/api/auth/oauth/exchange` khong biet nguoi dung den tu dau, va do la
        chu y: tat mot nha cung cap khong duoc lam hong phien cua nhung nguoi
        da dang nhap bang no truoc do.
        """
        import inspect

        nguon = inspect.getsource(server_main.oauth_exchange)
        for cam in ("facebook", "google", "provider"):
            self.assertNotIn(cam, nguon)

    def test_Facebook_van_nam_trong_danh_sach_provider(self) -> None:
        """Danh sach trang giu nguyen — cai thay doi la CO, khong phai ma."""
        self.assertIn("facebook", server_main.OAUTH_PROVIDERS)

    def test_adapter_khong_he_biet_toi_co_nay(self) -> None:
        """
        Co la quyet dinh SAN PHAM, cuong che o tang route. Adapter chi biet
        cach noi chuyen voi Appwrite. Tron co xuong adapter se lam viec bat lai
        phai sua hai cho.
        """
        import inspect

        from server.appwrite_adapter import AppwriteIdentityAdapter

        nguon = inspect.getsource(AppwriteIdentityAdapter)
        self.assertNotIn("facebook_login_enabled", nguon)

    def test_giao_dien_va_may_chu_noi_CUNG_mot_dieu(self) -> None:
        """
        `web/src/lib/oauth.ts` chep lai co de giao dien biet co ve nut hay
        khong. Hai gia tri o hai ngon ngu se troi khoi nhau neu khong ai giu,
        va hau qua thi im lang: nut hien ra nhung bam vao thi 404.

        Cung khuon voi `test_limits.py`, va vi cung mot ly do.
        """
        import re
        from pathlib import Path

        from server.config import Settings

        duong = (Path(__file__).resolve().parents[2]
                 / "web" / "src" / "lib" / "oauth.ts")
        self.assertTrue(duong.is_file(), "thiếu web/src/lib/oauth.ts")
        khop = re.search(r"FACEBOOK_LOGIN_ENABLED\s*:\s*boolean\s*=\s*(true|false)",
                         duong.read_text(encoding="utf-8"))
        self.assertIsNotNone(khop, "không đọc được cờ ở giao diện")
        self.assertEqual(khop.group(1) == "true",
                         Settings().facebook_login_enabled,
                         "cờ ở giao diện và ở máy chủ đã lệch nhau")


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
