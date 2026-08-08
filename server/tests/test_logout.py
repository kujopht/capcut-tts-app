"""
Dang xuat phai ket thuc phien o PHIA MAY CHU.

LOI DA GAP tren staging that: giao dien co nut "Dang xuat", nhung `signOut` chi
goi `setToken(null)` — xoa token trong localStorage. Backend KHONG co route
logout nao, va session secret cua Appwrite van song nguyen.

Bang chung do duoc: sau khi "dang xuat", goi lai `GET /api/auth/me` bang chinh
token do van tra 200.

Hau qua: tren may dung chung, "dang xuat" khong bao ve duoc gi. Ai nhat duoc
token (lich su, log, may chung) van dung tiep duoc cho den khi phien tu het han.

`MockIdentityAdapter.logout()` da ton tai san nhung la MA CHET: khong Protocol
nao khai bao, khong adapter that nao hien thuc, khong route nao goi.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import (IdentityAdapter, LocalStorageAdapter,
                             MockIdentityAdapter, MockMetadataStore)


class Base(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        server_main.store = MockMetadataStore()
        self._storage = server_main.storage
        server_main.storage = LocalStorageAdapter(Path(tempfile.mkdtemp()))
        self.client = TestClient(server_main.app)
        r = self.client.post("/api/auth/register",
                             json={"email": "tacgia@example.com",
                                   "password": "matkhau123"})
        self.token = r.json()["token"]
        self.head = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        server_main.storage = self._storage


class TestTheSessionEndsOnTheServer(Base):
    def test_the_route_exists(self):
        """Truoc ban sua, duong nay tra 404."""
        r = self.client.post("/api/auth/logout", headers=self.head)
        self.assertNotIn(r.status_code, (404, 405),
                         "phai co route POST /api/auth/logout")

    def test_the_token_works_before_logout(self):
        """Moc: neu buoc nay hong thi phep thu duoi khong noi len dieu gi."""
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.head).status_code, 200)

    def test_the_token_is_rejected_after_logout(self):
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.head).status_code, 200)
        self.client.post("/api/auth/logout", headers=self.head)
        self.assertEqual(
            self.client.get("/api/auth/me", headers=self.head).status_code, 401,
            "token phai het gia tri sau khi dang xuat")

    def test_every_private_route_rejects_the_token_after_logout(self):
        """Khong chi `/me` — moi duong rieng tu deu phai tu choi."""
        self.client.post("/api/auth/logout", headers=self.head)
        for duong in ("/api/auth/me", "/api/novels?mine=true",
                      "/api/chapters?mine=true", "/api/jobs"):
            with self.subTest(duong=duong):
                self.assertEqual(
                    self.client.get(duong, headers=self.head).status_code, 401)

    def test_it_reports_whether_the_session_was_revoked(self):
        r = self.client.post("/api/auth/logout", headers=self.head)
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["da_huy_phien"], True)

    def test_logging_out_twice_is_not_an_error(self):
        """Nguoi dung bam hai lan khong duoc nhan loi."""
        self.client.post("/api/auth/logout", headers=self.head)
        r = self.client.post("/api/auth/logout", headers=self.head)
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["da_huy_phien"], False,
                      "lan hai khong huy them phien nao")

    def test_logging_out_without_a_token_is_not_an_error(self):
        r = self.client.post("/api/auth/logout")
        self.assertEqual(r.status_code, 200, "khong duoc tra 401")
        self.assertIs(r.json()["da_huy_phien"], False)

    def test_a_garbage_token_is_not_an_error(self):
        r = self.client.post("/api/auth/logout",
                             headers={"Authorization": "Bearer rac"})
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["da_huy_phien"], False)

    def test_logout_does_not_touch_other_sessions(self):
        """Dang xuat mot phien khong duoc da nguoi dung khac ra ngoai."""
        r = self.client.post("/api/auth/register",
                             json={"email": "nguoikhac@example.com",
                                   "password": "matkhau123"})
        khac = {"Authorization": f"Bearer {r.json()['token']}"}
        self.client.post("/api/auth/logout", headers=self.head)
        self.assertEqual(self.client.get("/api/auth/me", headers=khac).status_code,
                         200, "phien cua nguoi khac phai con nguyen")

    def test_two_sessions_of_the_same_user_are_independent(self):
        """Dang nhap tren hai may: thoat may nay khong duoc da may kia ra."""
        r = self.client.post("/api/auth/login",
                             json={"email": "tacgia@example.com",
                                   "password": "matkhau123"})
        phien_hai = {"Authorization": f"Bearer {r.json()['token']}"}
        self.client.post("/api/auth/logout", headers=self.head)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.head).status_code,
                         401, "phien vua thoat phai het gia tri")
        self.assertEqual(self.client.get("/api/auth/me", headers=phien_hai).status_code,
                         200, "phien con lai phai con dung duoc")

    def test_login_still_works_after_logout(self):
        self.client.post("/api/auth/logout", headers=self.head)
        r = self.client.post("/api/auth/login",
                             json={"email": "tacgia@example.com",
                                   "password": "matkhau123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.client.get("/api/auth/me",
                            headers={"Authorization": f"Bearer {r.json()['token']}"}
                            ).status_code, 200)


class TestTheContractIsDeclaredEverywhere(unittest.TestCase):
    """
    `logout` tung ton tai o ban mock nhung khong o Protocol lan ban Appwrite —
    ma chet. Phep thu nay chan viec no lai roi vao trang thai do.
    """

    def test_the_protocol_declares_logout(self):
        self.assertTrue(hasattr(IdentityAdapter, "logout"),
                        "Protocol phai khai bao `logout`")

    def test_the_mock_implements_logout(self):
        self.assertTrue(callable(getattr(MockIdentityAdapter, "logout", None)))

    def test_the_appwrite_adapter_implements_logout(self):
        from server.appwrite_adapter import AppwriteIdentityAdapter

        self.assertTrue(callable(getattr(AppwriteIdentityAdapter, "logout", None)),
                        "ban Appwrite phai hien thuc `logout`, khong duoc de mock "
                        "lam mot dang con ban that lam mot dang")

    def test_the_appwrite_adapter_deletes_the_session(self):
        import inspect

        from server.appwrite_adapter import AppwriteIdentityAdapter

        nguon = inspect.getsource(AppwriteIdentityAdapter.logout)
        self.assertIn("/v1/account/sessions/current", nguon)
        self.assertIn('"DELETE"', nguon)
        self.assertIn("admin=False", nguon,
                      "phai goi bang chinh phien do, khong phai API key")

    def test_the_route_does_not_require_a_valid_session(self):
        """
        Dang xuat mot token da het han phai thanh cong, khong phai 401.

        Dung `current_profile` o day se lam nguoi dung het phien khong bam duoc
        "Dang xuat" — mot vong luan quan vo ly.
        """
        import inspect

        nguon = inspect.getsource(server_main.logout)
        self.assertNotIn("Depends(current_profile)", nguon)

    def test_the_route_does_not_swallow_every_error(self):
        import inspect

        nguon = inspect.getsource(server_main.logout)
        for rong in ("except Exception", "except BaseException", "except:"):
            self.assertNotIn(rong, nguon, f"khong duoc bat {rong}")


if __name__ == "__main__":
    unittest.main()
