"""
Test luong xuat ban novel: trang thai `published` phai duoc LUU BEN VUNG.

Vi sao can bo test nay: route `POST /api/novels/{id}/publish` truoc day chi doi
`novel.state` cua object trong bo nho va khong he goi kho metadata. Voi
`MockMetadataStore` thi van "dung" vi kho giu cung tham chieu - nhung voi
Appwrite, thao tac xuat ban mat trang, VA quyen doc cong khai khong bao gio
duoc mo. Day la dung mot loai loi voi vong doi TTS job (xem
`test_job_persistence.py`).

Chay HOAN TOAN offline: phan Appwrite dung client gia lap, khong cham mang va
khong can credential that.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional

from fastapi.testclient import TestClient

from server import main as server_main
from server.adapters import (
    MockIdentityAdapter,
    MockMetadataStore,
    NotFoundError,
    PermissionDenied,
)
from server.config import AppwriteSettings
from server.domain import Novel, PublishState


# -----------------------------------------------------------------------------
# Nen chung
# -----------------------------------------------------------------------------


class PublishTestCase(unittest.TestCase):
    def setUp(self) -> None:
        server_main.identity = MockIdentityAdapter()
        self.store = MockMetadataStore()
        server_main.store = self.store
        self.client = TestClient(server_main.app)

    def _auth(self, token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _user(self, email: str = "chu@example.com") -> str:
        return self.client.post(
            "/api/auth/register", json={"email": email, "password": "matkhau123"}
        ).json()["token"]

    def _novel(self, token: str, title: str = "Truyện") -> str:
        return self.client.post(
            "/api/novels", json={"title": title}, headers=self._auth(token)
        ).json()["novel"]["novel_id"]

    def _publish(self, token: str, novel_id: str, **kwargs):
        return self.client.post(
            f"/api/novels/{novel_id}/publish", headers=self._auth(token), **kwargs
        )


# -----------------------------------------------------------------------------
# 1-3: duong di thanh cong
# -----------------------------------------------------------------------------


class TestSuccessfulPublish(PublishTestCase):
    def test_1_owner_can_publish_a_draft_novel(self):
        token = self._user()
        novel_id = self._novel(token)
        self.assertEqual(self.store.get_novel(novel_id).state, PublishState.DRAFT)

        r = self._publish(token, novel_id)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["novel"]["state"], PublishState.PUBLISHED.value)

    def test_2_publish_is_saved_through_the_metadata_interface(self):
        """Route phai goi `store.publish_novel()`, khong tu doi object."""
        calls: List[tuple] = []

        class RecordingStore(MockMetadataStore):
            def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
                calls.append((novel_id, owner_id))
                return super().publish_novel(novel_id, owner_id)

        self.store = RecordingStore()
        server_main.store = self.store

        token = self._user()
        novel_id = self._novel(token)
        owner_id = self.client.get(
            "/api/auth/me", headers=self._auth(token)
        ).json()["profile"]["user_id"]

        self._publish(token, novel_id)
        self.assertEqual(
            calls, [(novel_id, owner_id)],
            "route phải đi qua metadata interface với owner lấy từ token",
        )

    def test_3_reading_the_novel_back_returns_published(self):
        """
        Doc lai phai thay `published` - khong phu thuoc object tam trong route.

        Doc bang MOT request khac hoan toan, qua endpoint cong khai.
        """
        token = self._user()
        novel_id = self._novel(token)
        self._publish(token, novel_id)

        # Doc lai qua HTTP (an danh, khong dung lai object nao cua route truoc)
        fetched = self.client.get(f"/api/novels/{novel_id}").json()["novel"]
        self.assertEqual(fetched["state"], PublishState.PUBLISHED.value)

        # Va doc thang tu kho metadata
        self.assertEqual(
            self.store.get_novel(novel_id).state, PublishState.PUBLISHED
        )

        # Va no phai xuat hien trong thu vien cong khai
        library = self.client.get("/api/novels").json()
        self.assertIn(novel_id, [n["novel_id"] for n in library["novels"]])


# -----------------------------------------------------------------------------
# 4-6: authorization
# -----------------------------------------------------------------------------


class TestPublishAuthorization(PublishTestCase):
    def test_4_non_owner_is_denied(self):
        owner = self._user("chu@example.com")
        novel_id = self._novel(owner)
        intruder = self._user("ke-xam-nhap@example.com")

        r = self._publish(intruder, novel_id)
        self.assertEqual(r.status_code, 403)
        # Va trang thai KHONG duoc doi
        self.assertEqual(self.store.get_novel(novel_id).state, PublishState.DRAFT)

    def test_5_forged_user_id_in_body_does_not_help(self):
        """Chu so huu lay tu token; body do client gui khong bao gio duoc tin."""
        owner = self._user("chu@example.com")
        novel_id = self._novel(owner)
        owner_id = self.client.get(
            "/api/auth/me", headers=self._auth(owner)
        ).json()["profile"]["user_id"]
        intruder = self._user("ke-xam-nhap@example.com")

        r = self._publish(
            intruder, novel_id,
            json={"owner_id": owner_id, "user_id": owner_id},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.store.get_novel(novel_id).state, PublishState.DRAFT)

    def test_5b_publish_requires_authentication(self):
        owner = self._user()
        novel_id = self._novel(owner)
        r = self.client.post(f"/api/novels/{novel_id}/publish")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.store.get_novel(novel_id).state, PublishState.DRAFT)

    def test_6_unknown_novel_returns_404(self):
        token = self._user()
        r = self._publish(token, "nov_khong_ton_tai")
        self.assertEqual(r.status_code, 404)

    def test_6b_unknown_novel_is_404_not_403(self):
        """Khong duoc lo thong tin bang cach tra 403 cho novel khong ton tai."""
        token = self._user()
        self.assertEqual(self._publish(token, "nov_bia_ra").status_code, 404)


# -----------------------------------------------------------------------------
# 7-8: idempotency va that bai khi luu
# -----------------------------------------------------------------------------


class TestIdempotencyAndFailure(PublishTestCase):
    def test_7_publishing_twice_is_idempotent(self):
        token = self._user()
        novel_id = self._novel(token)

        first = self._publish(token, novel_id)
        second = self._publish(token, novel_id)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200, "publish lại không được lỗi")
        self.assertEqual(
            second.json()["novel"]["state"], PublishState.PUBLISHED.value
        )
        self.assertEqual(
            first.json()["novel"]["novel_id"], second.json()["novel"]["novel_id"]
        )
        # Khong tao ban ghi trung
        self.assertEqual(len(self.store.novels), 1)
        self.assertEqual(self.client.get("/api/novels").json()["count"], 1)

    def test_8_persistence_failure_is_not_reported_as_success(self):
        class BrokenStore(MockMetadataStore):
            def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
                # Kiem quyen truoc roi moi hong o buoc GHI
                self.owned_novel(novel_id, owner_id)
                raise RuntimeError("metadata backend từ chối ghi")

        self.store = BrokenStore()
        server_main.store = self.store

        token = self._user()
        novel_id = self._novel(token)
        r = self._publish(token, novel_id)

        self.assertNotEqual(r.status_code, 200, "không được báo thành công giả")
        self.assertEqual(r.status_code, 502)
        # Trang thai local KHONG duoc doi thanh published
        self.assertEqual(self.store.get_novel(novel_id).state, PublishState.DRAFT)
        self.assertEqual(
            self.client.get(f"/api/novels/{novel_id}").json()["novel"]["state"],
            PublishState.DRAFT.value,
        )
        # Va no khong duoc lot vao thu vien cong khai
        self.assertEqual(self.client.get("/api/novels").json()["count"], 0)

    def test_8b_error_response_leaks_no_secret(self):
        class BrokenStore(MockMetadataStore):
            def publish_novel(self, novel_id: str, owner_id: str) -> Novel:
                self.owned_novel(novel_id, owner_id)
                raise RuntimeError("api_key=khong-duoc-lo-ra-ngoai")

        self.store = BrokenStore()
        server_main.store = self.store
        token = self._user()
        r = self._publish(token, self._novel(token))
        self.assertNotIn("khong-duoc-lo-ra-ngoai", r.text)


# -----------------------------------------------------------------------------
# 9: contract cua ban mock
# -----------------------------------------------------------------------------


class TestMockStoreContract(unittest.TestCase):
    """`MockMetadataStore.publish_novel()` phai tuan dung contract."""

    def setUp(self) -> None:
        self.store = MockMetadataStore()
        self.novel = self.store.create_novel(Novel(owner_id="usr_chu", title="T"))

    def test_9_unknown_novel_raises_not_found(self):
        with self.assertRaises(NotFoundError):
            self.store.publish_novel("nov_khong_co", "usr_chu")

    def test_9_wrong_owner_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            self.store.publish_novel(self.novel.novel_id, "usr_khac")

    def test_9_publish_persists_and_is_readable(self):
        result = self.store.publish_novel(self.novel.novel_id, "usr_chu")
        self.assertEqual(result.state, PublishState.PUBLISHED)
        self.assertEqual(
            self.store.get_novel(self.novel.novel_id).state, PublishState.PUBLISHED
        )

    def test_9_publish_is_idempotent(self):
        a = self.store.publish_novel(self.novel.novel_id, "usr_chu")
        b = self.store.publish_novel(self.novel.novel_id, "usr_chu")
        self.assertEqual(a.novel_id, b.novel_id)
        self.assertEqual(b.state, PublishState.PUBLISHED)
        self.assertEqual(len(self.store.novels), 1)

    def test_9_failed_publish_leaves_stored_record_intact(self):
        """Sai chu so huu -> ban ghi dang luu khong duoc doi mot chut nao."""
        before = self.store.get_novel(self.novel.novel_id)
        with self.assertRaises(PermissionDenied):
            self.store.publish_novel(self.novel.novel_id, "usr_khac")
        after = self.store.get_novel(self.novel.novel_id)
        self.assertEqual(after.state, PublishState.DRAFT)
        self.assertEqual(after.updated_at, before.updated_at)

    def test_9_mock_store_is_documented_as_non_durable(self):
        """Ban mock khong duoc mo ta nhu kho ben vung."""
        doc = (MockMetadataStore.__doc__ or "").upper()
        self.assertIn("KHONG PHAI KHO BEN VUNG", doc)

    def test_9_mock_and_appwrite_share_the_same_signature(self):
        import inspect

        from server.appwrite_store import AppwriteMetadataStore

        self.assertEqual(
            list(inspect.signature(AppwriteMetadataStore.publish_novel).parameters),
            list(inspect.signature(MockMetadataStore.publish_novel).parameters),
            "hai kho metadata phải cùng chữ ký publish_novel()",
        )

    def test_9_protocol_declares_publish_novel(self):
        from server.adapters import MetadataStore

        self.assertTrue(
            callable(getattr(MetadataStore, "publish_novel", None)),
            "publish_novel phải nằm trong protocol MetadataStore chính thức",
        )


# -----------------------------------------------------------------------------
# 10-12: Appwrite adapter voi client gia lap
# -----------------------------------------------------------------------------


class _FakeAppwriteClient:
    """Client Appwrite toi gian trong bo nho. Khong cham mang."""

    def __init__(self, documents: Dict[str, Dict[str, Any]]):
        self.documents = documents
        self.requests: List[Dict[str, Any]] = []

    def request(self, method: str, url: str, json: Optional[Dict] = None,
                params: Optional[Dict] = None,
                headers: Optional[Dict] = None) -> Dict[str, Any]:
        self.requests.append({"method": method, "url": url,
                              "payload": json, "headers": headers})
        doc_id = url.rsplit("/", 1)[-1]
        if method == "GET":
            if doc_id not in self.documents:
                raise NotFoundError("Không tìm thấy bản ghi.")
            return dict(self.documents[doc_id])
        if method == "PATCH":
            doc = self.documents[doc_id]
            doc.update(json.get("data") or {})
            if json.get("permissions") is not None:
                doc["$permissions"] = list(json["permissions"])
            return dict(doc)
        return {}

    # -- tien ich -------------------------------------------------------------

    @property
    def patches(self) -> List[Dict[str, Any]]:
        return [r for r in self.requests if r["method"] == "PATCH"]


def _draft_doc(novel_id: str, owner_id: str) -> Dict[str, Any]:
    return {
        "novel_id": novel_id, "owner_id": owner_id, "title": "Truyện",
        "description": "", "cover_key": None, "state": "draft", "tags": [],
        "created_at": "2026-08-06T00:00:00+00:00",
        "updated_at": "2026-08-06T00:00:00+00:00",
    }


class TestAppwritePublishWithMockedClient(unittest.TestCase):
    OWNER = "usr_chu"
    NOVEL = "nov_abc"

    def _store(self, documents=None):
        from server.appwrite_store import AppwriteMetadataStore

        docs = documents if documents is not None else {
            self.NOVEL: _draft_doc(self.NOVEL, self.OWNER)
        }
        self.fake = _FakeAppwriteClient(docs)
        # Gia tri gia, KHONG phai credential that
        settings = AppwriteSettings(
            endpoint="https://khong-co-that.example/v1",
            project_id="du-an-gia", api_key="khoa-gia", database_id="db-gia",
        )
        return AppwriteMetadataStore(settings, client=self.fake)

    def test_10_update_is_called_with_published_state_and_permissions(self):
        store = self._store()
        novel = store.publish_novel(self.NOVEL, self.OWNER)

        self.assertEqual(novel.state, PublishState.PUBLISHED)
        self.assertEqual(len(self.fake.patches), 1,
                         "phải cập nhật trong đúng MỘT request (nguyên tử)")

        payload = self.fake.patches[0]["payload"]
        self.assertEqual(payload["data"]["state"], "published")
        self.assertTrue(payload["data"]["updated_at"])
        self.assertIn("permissions", payload,
                      "phải gửi kèm permissions trong cùng request")

    def test_10b_permissions_and_data_travel_in_the_same_request(self):
        """Neu tach lam hai request se co cua so trang thai/quyen lech nhau."""
        store = self._store()
        store.publish_novel(self.NOVEL, self.OWNER)
        patch = self.fake.patches[0]
        self.assertIn("data", patch["payload"])
        self.assertIn("permissions", patch["payload"])

    def test_11_published_novel_has_public_read_but_no_public_write(self):
        store = self._store()
        store.publish_novel(self.NOVEL, self.OWNER)
        perms = self.fake.patches[0]["payload"]["permissions"]

        self.assertIn('read("any")', perms, "truyện đã xuất bản phải cho đọc công khai")
        for owner_perm in (f'read("user:{self.OWNER}")',
                           f'update("user:{self.OWNER}")',
                           f'delete("user:{self.OWNER}")'):
            self.assertIn(owner_perm, perms)

        for forbidden in ('update("any")', 'delete("any")', 'write("any")',
                          'create("any")'):
            self.assertNotIn(forbidden, perms,
                             f"tuyệt đối không mở {forbidden} cho công khai")
        # Khong quyen nao khac ngoai `read` duoc cap cho pham vi cong khai
        public = [p for p in perms if p.endswith('("any")')]
        self.assertEqual(public, ['read("any")'])

    def test_12_draft_novel_is_not_publicly_readable(self):
        """Novel tao moi (draft) chi chu so huu doc/sua duoc."""
        store = self._store(documents={})
        store.create_novel(Novel(novel_id=self.NOVEL, owner_id=self.OWNER, title="T"))

        created = [r for r in self.fake.requests if r["method"] == "POST"][0]
        perms = created["payload"]["permissions"]
        self.assertNotIn('read("any")', perms, "bản nháp không được đọc công khai")
        self.assertEqual([p for p in perms if p.endswith('("any")')], [])
        self.assertIn(f'read("user:{self.OWNER}")', perms)

    def test_12b_non_owner_is_denied_before_any_write(self):
        store = self._store()
        with self.assertRaises(PermissionDenied):
            store.publish_novel(self.NOVEL, "usr_ke_xam_nhap")
        self.assertEqual(self.fake.patches, [],
                         "bị từ chối thì không được gửi request ghi nào")
        self.assertEqual(self.fake.documents[self.NOVEL]["state"], "draft")

    def test_12c_publish_is_idempotent_on_appwrite(self):
        store = self._store()
        store.publish_novel(self.NOVEL, self.OWNER)
        store.publish_novel(self.NOVEL, self.OWNER)

        self.assertEqual(len(self.fake.patches), 2, "PATCH, không phải tạo mới")
        self.assertEqual(
            [r for r in self.fake.requests if r["method"] == "POST"], [],
            "publish lại không được tạo bản ghi trùng",
        )
        self.assertEqual(self.fake.documents[self.NOVEL]["state"], "published")
        # Ap lai quyen -> tu chua neu quyen bi lech
        self.assertIn('read("any")', self.fake.documents[self.NOVEL]["$permissions"])

    def test_12d_api_key_stays_server_side(self):
        """API key chi nam trong header goi Appwrite, khong o du lieu tra ve."""
        store = self._store()
        novel = store.publish_novel(self.NOVEL, self.OWNER)

        self.assertIn("X-Appwrite-Key", self.fake.patches[0]["headers"])
        self.assertNotIn("khoa-gia", str(novel.to_dict()))


# -----------------------------------------------------------------------------
# 13: luong Creator Studio dau-cuoi
# -----------------------------------------------------------------------------


class TestCreatorStudioFlow(PublishTestCase):
    def test_13_full_publish_flow_still_works(self):
        """Dang ky -> novel -> chuong -> publish -> hien trong thu vien cong khai."""
        token = self._user("tacgia@example.com")
        novel_id = self._novel(token, "Hải Tặc Mũ Rơm")
        chapter_id = self.client.post(
            "/api/chapters",
            json={"novel_id": novel_id, "title": "Chương 1", "content": "Nội dung."},
            headers=self._auth(token),
        ).json()["chapter"]["chapter_id"]

        # Truoc khi xuat ban: khong nam trong thu vien cong khai
        self.assertEqual(self.client.get("/api/novels").json()["count"], 0)

        r = self._publish(token, novel_id)
        self.assertEqual(r.status_code, 200)

        # Sau khi xuat ban: an danh cung thay
        library = self.client.get("/api/novels").json()
        self.assertEqual(library["count"], 1)
        self.assertEqual(library["novels"][0]["state"], "published")

        detail = self.client.get(f"/api/novels/{novel_id}").json()
        self.assertEqual(detail["novel"]["state"], "published")
        self.assertEqual(
            [c["chapter_id"] for c in detail["chapters"]], [chapter_id]
        )

        # Danh sach cua rieng minh van hoat dong
        mine = self.client.get(
            "/api/novels?mine=true", headers=self._auth(token)
        ).json()
        self.assertEqual(mine["count"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
