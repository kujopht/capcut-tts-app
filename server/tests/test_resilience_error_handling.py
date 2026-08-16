"""
Phase 10 (overnight hardening) - kiem thu chiu loi/resilience.

Muc tieu: MOI tinh nang phai that bai MOT CACH SACH SE khi phu thuoc ben
ngoai (Appwrite, YouTube Data API) khong the ket noi/timeout - dung ma HTTP,
thong bao huu ich, KHONG lo secret, KHONG traceback Python tho, KHONG ket
qua "ket dinh vinh vien".

Toan bo test o day chay OFFLINE: khong cham Appwrite/YouTube that. Ket noi
Appwrite bi "cat" bang cach thay `AppwriteIdentityAdapter._client` bang mot
doi tuong gia nem `httpx.ConnectError` - dung mo hinh boc client da co san o
`test_appwrite_v2_contract.py` (tham so `client=` cua `AppwriteMetadataStore`),
o day ap dung cho `AppwriteIdentityAdapter` (khong co tham so `client=` san,
nen ta gan thang vao thuoc tinh `_client` sau khi khoi tao - cach nay khong
dung API rieng nao khac ngoai field da co).
"""

from __future__ import annotations

import unittest

import httpx
from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import AuthError, MockIdentityAdapter, MockMetadataStore
from server.appwrite_adapter import AppwriteIdentityAdapter
from server.config import AppwriteSettings


class _FakeCookies:
    def clear(self) -> None:
        return None


class _FakeConnectErrorClient:
    """Gia lap `httpx.Client` khi Appwrite khong the ket noi (host chet,
    DNS loi, mang bi ngat...)."""

    def __init__(self) -> None:
        self.cookies = _FakeCookies()

    def request(self, method, url, json=None, params=None, headers=None):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")


def _appwrite_identity_khong_ket_noi_duoc() -> AppwriteIdentityAdapter:
    cfg = AppwriteSettings(
        endpoint="https://appwrite-khong-ton-tai.invalid/v1",
        project_id="p", api_key="secret-api-key-khong-duoc-lo", database_id="db",
    )
    adapter = AppwriteIdentityAdapter(cfg)
    adapter._client = _FakeConnectErrorClient()  # "cat mang" - xem docstring module
    return adapter


class KichBanAppwriteKhongKetNoiDuoc(unittest.TestCase):
    """Kich ban 1: Appwrite khong the ket noi (mang loi/DNS/host chet)."""

    def setUp(self) -> None:
        self._identity_cu = server_main.identity
        self._store_cu = server_main.store
        server_main.identity = _appwrite_identity_khong_ket_noi_duoc()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.identity = self._identity_cu
        server_main.store = self._store_cu

    def test_dang_nhap_khi_appwrite_mat_ket_noi_tra_ve_503(self):
        r = self.client.post("/api/auth/login",
                             json={"email": "a@example.com", "password": "matkhau123"})
        self.assertEqual(r.status_code, 503, r.text)
        body = r.json()
        self.assertIn("detail", body)

    def test_dang_nhap_khong_lo_dia_chi_appwrite_hay_api_key(self):
        r = self.client.post("/api/auth/login",
                             json={"email": "a@example.com", "password": "matkhau123"})
        text = r.text
        self.assertNotIn("appwrite-khong-ton-tai.invalid", text)
        self.assertNotIn("secret-api-key-khong-duoc-lo", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn("getaddrinfo", text)

    def test_goi_route_bao_ve_khi_appwrite_mat_ket_noi_tra_ve_503(self):
        r = self.client.get("/api/auth/me", headers={"Authorization": "Bearer bat-ky-token-nao"})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertNotIn("Traceback", r.text)

    def test_dang_ky_khi_appwrite_mat_ket_noi_tra_ve_503(self):
        r = self.client.post("/api/auth/register",
                             json={"email": "b@example.com", "password": "matkhau123"})
        self.assertEqual(r.status_code, 503, r.text)
        self.assertNotIn("Traceback", r.text)

    def test_dang_xuat_van_tra_200_khi_appwrite_mat_ket_noi(self):
        """Dang xuat PHAI luon tra 200 (client tu xoa token cuc bo) bat ke
        Appwrite con song hay khong - xem docstring `logout()` trong main.py."""
        r = self.client.post("/api/auth/logout",
                             headers={"Authorization": "Bearer bat-ky-token-nao"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("da_huy_phien"), False)

    def test_khong_co_trang_thai_ket_dinh_vinh_vien_sau_khi_appwrite_phuc_hoi(self):
        """Sau khi 'mang duoc noi lai' (doi ve MockIdentityAdapter), request
        moi phai chay binh thuong tro lai - khong con trang thai loi treo lai."""
        server_main.identity = MockIdentityAdapter()
        r = self.client.post("/api/auth/register",
                             json={"email": "c@example.com", "password": "matkhau123"})
        self.assertEqual(r.status_code, 201, r.text)


class KichBanRequestSaiDinhDang(unittest.TestCase):
    """Kich ban 4: request body sai dinh dang (thieu truong bat buoc / sai kieu)."""

    def setUp(self) -> None:
        self._identity_cu = server_main.identity
        self._store_cu = server_main.store
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.identity = self._identity_cu
        server_main.store = self._store_cu

    def _dang_ky(self, email="d@example.com", password="matkhau123") -> str:
        r = self.client.post("/api/auth/register", json={"email": email, "password": password})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["token"]

    def test_dang_ky_thieu_truong_bat_buoc_tra_422_khong_traceback(self):
        r = self.client.post("/api/auth/register", json={"email": "e@example.com"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertNotIn("Traceback", r.text)
        self.assertNotIn("site-packages", r.text)

    def test_dang_ky_sai_kieu_du_lieu_tra_422_khong_traceback(self):
        r = self.client.post("/api/auth/register",
                             json={"email": 12345, "password": True})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertNotIn("Traceback", r.text)

    def test_body_khong_phai_json_tra_loi_sach(self):
        r = self.client.post(
            "/api/auth/register",
            data=b"day khong phai json {{{",
            headers={"Content-Type": "application/json"},
        )
        self.assertIn(r.status_code, (400, 422), r.text)
        self.assertNotIn("Traceback", r.text)

    def test_tao_novel_thieu_truong_bat_buoc_tra_422(self):
        token = self._dang_ky()
        r = self.client.post("/api/novels", json={},
                             headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r.status_code, 422, r.text)
        self.assertNotIn("Traceback", r.text)

    def test_tao_chuong_sai_kieu_du_lieu_tra_422(self):
        token = self._dang_ky(email="f@example.com")
        r = self.client.post(
            "/api/chapters",
            json={"novel_id": 123, "title": None, "content": ["khong phai chuoi"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(r.status_code, 422, r.text)
        self.assertNotIn("Traceback", r.text)


class KichBanDangNhapPhienHetHan(unittest.TestCase):
    """Kich ban 8: token het han/rac dung cho route duoc bao ve."""

    def setUp(self) -> None:
        self._identity_cu = server_main.identity
        self._store_cu = server_main.store
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.identity = self._identity_cu
        server_main.store = self._store_cu

    def test_token_rac_tra_401_khong_traceback(self):
        r = self.client.get("/api/auth/me",
                             headers={"Authorization": "Bearer token-rac-hoan-toan-khong-hop-le"})
        self.assertEqual(r.status_code, 401, r.text)
        self.assertNotIn("Traceback", r.text)

    def test_token_da_dang_xuat_khong_con_dung_duoc(self):
        r = self.client.post("/api/auth/register",
                             json={"email": "g@example.com", "password": "matkhau123"})
        token = r.json()["token"]
        r2 = self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r2.status_code, 200, r2.text)
        r3 = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r3.status_code, 401, r3.text)

    def test_khong_co_header_authorization_tra_401_khong_500(self):
        r = self.client.get("/api/auth/me")
        self.assertEqual(r.status_code, 401, r.text)
        self.assertNotIn("Traceback", r.text)


class KichBanAdminBiTuChoi(unittest.TestCase):
    """Kich ban 9: nguoi dung thuong goi route /api/admin/* - CHI kiem phan
    hoi co sach (khong lo chi tiet noi bo) hay khong, khong kiem lai quyen han
    (da xac minh sach o Phase 3)."""

    def setUp(self) -> None:
        self._identity_cu = server_main.identity
        self._store_cu = server_main.store
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.identity = self._identity_cu
        server_main.store = self._store_cu

    def test_nguoi_dung_thuong_goi_admin_overview_tra_403_khong_traceback(self):
        r = self.client.post("/api/auth/register",
                             json={"email": "h@example.com", "password": "matkhau123"})
        token = r.json()["token"]
        r2 = self.client.get("/api/admin/overview", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(r2.status_code, 403, r2.text)
        body = r2.json()
        self.assertIn("detail", body)
        self.assertIsInstance(body["detail"], str)
        self.assertNotIn("Traceback", r2.text)
        self.assertNotIn("site-packages", r2.text)
        self.assertNotIn("File \"", r2.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
