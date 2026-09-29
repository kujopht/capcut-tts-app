"""
Kiem thu Tiered Rate Limiting Middleware.

Moi tran nho dat bang `mock.patch.dict(os.environ, ...)`: ra khoi khoi `with` la gia tri CU duoc tra lai
(khong `pop`). `server/tests/__init__.py` dat tran rat cao cho ca tien trinh test — `pop` o day tung xoa no
va lam moi module chay sau lai 429 (xem ghi chu o `__init__.py`).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient
from starlette.requests import Request

from server import main as server_main
from server.adapters import LocalStorageAdapter, MockIdentityAdapter, MockMetadataStore
from server.rate_limit import TIER_A, TIER_B, TIER_C, classify_request, limiter


class TestRateLimiting(unittest.TestCase):
    def setUp(self) -> None:
        limiter.reset()
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._real_storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)

    def tearDown(self) -> None:
        server_main.storage = self._real_storage
        limiter.reset()

    def test_luu_ho_so_tinh_theo_gio_va_bi_chan_khi_vuot(self):
        """Social & Play V1: PUT /api/me/profile + PUT /api/creator/avatar dung Tier PROFILE (theo GIO)."""
        os.environ["FAS_RATE_LIMIT_PROFILE_PER_HOUR"] = "2"
        try:
            h = {"Authorization": "Bearer tok_khong_ton_tai_1"}
            for _ in range(2):
                r = self.client.put("/api/me/profile", json={"bio": "x"}, headers=h)
                self.assertNotEqual(r.status_code, 429)
            r = self.client.put("/api/creator/avatar", json={}, headers=h)
            self.assertEqual(r.status_code, 429, "avatar dung chung han muc luu ho so")
            body = r.json()
            self.assertEqual(body["tier"], "tier_profile")
            self.assertGreater(int(r.headers["Retry-After"]), 60, "cua so la mot GIO, khong phai 60s")
        finally:
            os.environ.pop("FAS_RATE_LIMIT_PROFILE_PER_HOUR", None)

    def test_don_dep_khong_xoa_lich_su_cua_khoa_theo_gio(self):
        """Mot request 60s kich hoat don dep KHONG duoc xoa lich su cua mot khoa tinh theo GIO."""
        from server.rate_limit import SlidingWindowRateLimiter
        import time as _time

        lim = SlidingWindowRateLimiter()
        self.assertTrue(lim.check("tier_profile:u1", 1, window=3600.0)[0])
        # Gia lap: lan don dep ke tiep xay ra 10 phut sau, do mot request 60s kich hoat.
        lim._last_prune = _time.monotonic() - 61
        lim._history["tier_profile:u1"] = [_time.monotonic() - 600]
        lim.check("tier_b:u2", 100, window=60.0)
        self.assertFalse(lim.check("tier_profile:u1", 1, window=3600.0)[0],
                         "lich su theo gio bi don mat -> han muc tu reset")

    def test_healthcheck_is_excluded_from_rate_limits(self):
        """Endpoint /api/health tuyet doi khong bao gio bi rate limit."""
        for _ in range(50):
            r = self.client.get("/api/health")
            self.assertEqual(r.status_code, 200)

    def test_tier_a_limit_triggers_429(self):
        """Tier A (nhu login / dang ky) phai bi chan khi vuot qua han muc."""
        with mock.patch.dict(os.environ, {"FAS_RATE_LIMIT_TIER_A": "3"}):
            # 3 requests hop le
            for i in range(3):
                r = self.client.post("/api/auth/login", json={"email": f"test{i}@example.com", "password": "wrong"})
                self.assertNotEqual(r.status_code, 429)

            # Request thu 4 vuot han muc -> 429
            r_blocked = self.client.post("/api/auth/login", json={"email": "blocked@example.com", "password": "wrong"})
            self.assertEqual(r_blocked.status_code, 429)
            self.assertIn("Retry-After", r_blocked.headers)
            self.assertEqual(r_blocked.headers.get("X-RateLimit-Remaining"), "0")
            body = r_blocked.json()
            self.assertEqual(body["error"], "rate_limit_exceeded")
            self.assertEqual(body["tier"], "tier_a")

    def test_authenticated_users_have_independent_quotas(self):
        """Hai user khac nhau (dua tren Bearer token) co han muc rieng biet."""
        with mock.patch.dict(os.environ, {"FAS_RATE_LIMIT_TIER_A": "2"}):
            token_1 = "token_user_one_12345"
            token_2 = "token_user_two_67890"

            # User 1 dung het quota Tier A
            h1 = {"Authorization": f"Bearer {token_1}"}
            self.client.delete("/api/novels/nov_123", headers=h1)
            self.client.delete("/api/novels/nov_123", headers=h1)
            r3 = self.client.delete("/api/novels/nov_123", headers=h1)
            self.assertEqual(r3.status_code, 429)

            # User 2 van con nguyen quota
            h2 = {"Authorization": f"Bearer {token_2}"}
            r_user2 = self.client.delete("/api/novels/nov_456", headers=h2)
            self.assertNotEqual(r_user2.status_code, 429)

    def test_cf_connecting_ip_header_is_used(self):
        """Header CF-Connecting-IP duoc dung de phan biet cac dia chi IP khach."""
        with mock.patch.dict(os.environ, {"FAS_RATE_LIMIT_TIER_C": "2"}):
            self.client.get("/api/novels", headers={"CF-Connecting-IP": "1.2.3.4"})
            self.client.get("/api/novels", headers={"CF-Connecting-IP": "1.2.3.4"})
            r3 = self.client.get("/api/novels", headers={"CF-Connecting-IP": "1.2.3.4"})
            self.assertEqual(r3.status_code, 429)

            # IP khac van truy cap binh thuong
            r_other = self.client.get("/api/novels", headers={"CF-Connecting-IP": "5.6.7.8"})
            self.assertEqual(r_other.status_code, 200)

    def test_normal_public_reads_do_not_trip_limits(self):
        """Doc public danh muc o toc do thong thuong (10 requests) khong bi chan."""
        for _ in range(10):
            r = self.client.get("/api/novels")
            self.assertEqual(r.status_code, 200)
            self.assertIn("X-RateLimit-Remaining", r.headers)

    def test_tran_nho_cua_test_duoc_tra_lai_gia_tri_cu(self):
        """Ra khoi mot tran nho, tien trinh test VAN co tran cao cua `server/tests/__init__.py`."""
        truoc = os.environ.get("FAS_RATE_LIMIT_TIER_A")
        with mock.patch.dict(os.environ, {"FAS_RATE_LIMIT_TIER_A": "1"}):
            self.assertEqual(os.environ["FAS_RATE_LIMIT_TIER_A"], "1")
        self.assertEqual(os.environ.get("FAS_RATE_LIMIT_TIER_A"), truoc)

    def test_mac_dinh_production_khong_doi(self):
        """Khong co bien moi truong nao (nhu production): 60 / 120 / 600 — tran cao chi cua bo test."""
        def phan_loai(method: str, path: str):
            return classify_request(Request({"type": "http", "method": method, "path": path, "headers": [],
                                             "query_string": b""}))

        with mock.patch.dict(os.environ, {}):
            for ten in ("FAS_RATE_LIMIT_TIER_A", "FAS_RATE_LIMIT_TIER_B", "FAS_RATE_LIMIT_TIER_C"):
                os.environ.pop(ten, None)
            self.assertEqual(phan_loai("POST", "/api/auth/login"), (TIER_A, 60))
            self.assertEqual(phan_loai("POST", "/api/community/posts"), (TIER_B, 120))
            self.assertEqual(phan_loai("GET", "/api/novels"), (TIER_C, 600))
