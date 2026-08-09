"""
Test quyen truy cap tren Appwrite - chong tu nang quota/tier.

BOI CANH: "trinh duyet khong goi thang Appwrite nen chua khai thac duoc" la
lap luan KHONG du an toan. Nguoi dung nam session/JWT hop le hoan toan co the
goi Appwrite API ngoai giao dien. Vi vay quyen o muc document phai tu no dung,
khong duoc dua vao viec client "khong biet duong".

Hai tang quyen deu duoc kiem o day:
  1. muc COLLECTION (scripts/setup_appwrite.py)
  2. muc DOCUMENT   (server/appwrite_adapter.py, server/appwrite_store.py)

Quyen o muc collection ap dung THEM vao quyen document, nen mot collection
permission qua rong se vo hieu hoa toan bo mo hinh phan quyen theo document.

Chay offline, khong can credential.
"""

from __future__ import annotations

import re
import unittest
from typing import Any, Dict, List

from server.appwrite_adapter import profile_permissions
from server.appwrite_store import AppwriteMetadataStore
from server.config import AppwriteSettings
from server.domain import AudioTrack, Chapter, Novel, TtsJob

USER = "usr_nguoi_dung"

#: Truong do SERVER quyet dinh - client khong bao gio duoc ghi thang.
SERVER_AUTHORITATIVE = {
    "profiles": ("tier", "listened_minutes", "tts_characters_used"),
    "novels": ("state",),
    "tts_jobs": ("status", "output_key"),
    "audio_tracks": ("object_key",),
}


def _scopes(permissions: List[str]) -> List[str]:
    """['read("user:x")'] -> ['read']"""
    return [p.split("(", 1)[0] for p in permissions]


class TestProfileDocumentPermissions(unittest.TestCase):
    """`profiles` chua tier va cac bo dem quota."""

    def setUp(self) -> None:
        self.perms = profile_permissions(USER)

    def test_owner_has_read(self):
        """Thiet ke hien tai van cho chu ho so doc ho so cua chinh minh."""
        self.assertIn(f'read("user:{USER}")', self.perms)

    def test_owner_has_no_update(self):
        self.assertNotIn(f'update("user:{USER}")', self.perms)
        self.assertNotIn("update", _scopes(self.perms))

    def test_owner_has_no_delete(self):
        self.assertNotIn(f'delete("user:{USER}")', self.perms)
        self.assertNotIn("delete", _scopes(self.perms))

    def test_no_public_read_or_write(self):
        for permission in self.perms:
            self.assertNotIn('("any")', permission,
                             "hồ sơ không bao giờ được công khai")
            self.assertNotIn('("users")', permission,
                             "hồ sơ không được mở cho mọi người dùng đã đăng nhập")

    def test_only_read_scope_is_granted(self):
        self.assertEqual(_scopes(self.perms), ["read"])

    def test_permissions_are_scoped_to_that_one_user(self):
        other = profile_permissions("usr_nguoi_khac")
        self.assertNotEqual(self.perms, other)
        self.assertNotIn(f'read("user:{USER}")', other)

    def test_quota_fields_are_not_client_writable(self):
        """Khong co quyen ghi nao => khong the tu doi tier/quota qua Appwrite."""
        writable = [p for p in self.perms
                    if p.split("(", 1)[0] in ("update", "delete", "write", "create")]
        self.assertEqual(
            writable, [],
            f"các trường {SERVER_AUTHORITATIVE['profiles']} chỉ được sửa qua backend",
        )


class TestDocumentPermissionsAcrossCollections(unittest.TestCase):
    """
    novels / chapters / tts_jobs / audio_tracks cung chua truong server-authoritative.

    Vi du ro nhat: `audio_tracks.object_key`. Neu chu so huu con quyen `update`
    tren document cua chinh minh, ho chi can doi `object_key` sang key cua
    nguoi khac la `/api/audio/{chapter}` se phuc vu audio cua nguoi do - vuot
    qua ca `_may_listen()`.
    """

    def _permissions(self, public_read: bool = False) -> List[str]:
        return AppwriteMetadataStore._owner_permissions(USER, public_read=public_read)

    def test_draft_document_grants_owner_read_only(self):
        self.assertEqual(self._permissions(), [f'read("user:{USER}")'])

    def test_draft_document_has_no_public_read(self):
        self.assertNotIn('read("any")', self._permissions())

    def test_no_owner_update_or_delete(self):
        for public_read in (False, True):
            perms = self._permissions(public_read=public_read)
            self.assertNotIn("update", _scopes(perms))
            self.assertNotIn("delete", _scopes(perms))

    def test_published_adds_public_read_only(self):
        perms = self._permissions(public_read=True)
        self.assertIn('read("any")', perms)
        self.assertEqual(set(_scopes(perms)), {"read"})

    def test_never_grants_write_to_any_or_users_scope(self):
        for public_read in (False, True):
            for permission in self._permissions(public_read=public_read):
                scope, target = permission.split("(", 1)
                if target.startswith('"any"') or target.startswith('"users"'):
                    self.assertEqual(
                        scope, "read",
                        f"chỉ được cấp read cho phạm vi rộng, gặp {permission}",
                    )


class TestCollectionLevelPermissions(unittest.TestCase):
    """
    Quyen o muc collection ap dung THEM vao quyen document.

    Truoc day day la `create("users")`: bat ky nguoi dung da dang nhap nao
    cung tu tao document truc tiep o CA NAM collection, bo qua backend. Ke tan
    cong co the tu tao mot `audio_tracks` tro toi chuong cua nguoi khac va
    thay the audio duoc phuc vu, vi `track_for_chapter()` lay ban moi nhat.
    """

    def _collection_permissions(self):
        from scripts.setup_appwrite import COLLECTION_PERMISSIONS

        return COLLECTION_PERMISSIONS

    def test_collection_grants_nothing_to_clients(self):
        self.assertEqual(
            list(self._collection_permissions()), [],
            "quyền ở mức collection phải rỗng - mọi ghi đều qua API key",
        )

    def test_no_create_for_authenticated_users(self):
        for permission in self._collection_permissions():
            self.assertNotIn('create("users")', permission)
            self.assertNotIn('create("any")', permission)

    def test_collection_permissions_never_widen_document_permissions(self):
        """Khong quyen GHI nao duoc cap o muc collection."""
        for permission in self._collection_permissions():
            scope = permission.split("(", 1)[0]
            self.assertNotIn(scope, ("create", "update", "delete", "write"))

    def test_document_security_stays_enabled(self):
        """Tat documentSecurity se lam quyen tung document mat tac dung."""
        import inspect

        from scripts import setup_appwrite

        source = inspect.getsource(setup_appwrite.Setup.ensure_collection)
        self.assertIn('"documentSecurity": True', source)


class TestQuotaFieldsOnlyChangeServerSide(unittest.TestCase):
    """Cac truong server-authoritative chi doi qua adapter phia server."""

    def test_profile_document_carries_the_quota_fields(self):
        """Neu cac truong nay roi khoi profiles thi test quyen phai duoc xem lai."""
        from server.domain import Profile

        data = Profile(user_id=USER, email="a@b.c").to_dict()
        for field in SERVER_AUTHORITATIVE["profiles"]:
            self.assertIn(field, data)

    def test_server_authoritative_fields_exist_where_expected(self):
        self.assertIn("state", Novel(owner_id=USER, title="T").to_dict())
        self.assertIn("status", TtsJob(owner_id=USER, chapter_id="c",
                                       voice_id="v", content_hash="h").to_dict())
        self.assertIn("output_key", TtsJob(owner_id=USER, chapter_id="c",
                                           voice_id="v", content_hash="h").to_dict())
        self.assertIn("object_key", AudioTrack(chapter_id="c", owner_id=USER,
                                               voice_id="v", object_key="k",
                                               content_hash="h").to_dict())
        self.assertIn("owner_id", Chapter(novel_id="n", owner_id=USER,
                                          title="T").to_dict())

    #: Cac route POST duoi `/api/auth` da duoc soi va xac nhan KHONG ghi truong
    #: ho so nao. Them ten vao day la mot quyet dinh co y thuc, khong phai thao
    #: tac lam cho test xanh.
    AUTH_POST_DA_SOI = {
        "/api/auth/register",   # tao ho so moi, khong sua ho so co san
        "/api/auth/login",      # chi doi session, khong cham `profiles`
        "/api/auth/logout",     # chi xoa session o Appwrite
        # Doi cap OAuth dung-mot-lan lay session. CO ghi `profiles`, nhung chi
        # TAO khi chua co va KHONG BAO GIO ghi de — chung minh o
        # `test_oauth_exchange_only_creates_never_overwrites` ngay duoi.
        "/api/auth/oauth/exchange",
    }

    def test_no_backend_route_lets_a_client_write_profile_fields(self):
        """San pham hien chua co chuc nang sua ho so - khong co route ghi nao."""
        from server import main as server_main

        profile_writes = [
            route for route in server_main.app.routes
            if getattr(route, "path", "").startswith("/api/auth")
            and "POST" in (getattr(route, "methods", None) or set())
            and route.path not in self.AUTH_POST_DA_SOI
        ]
        self.assertEqual(
            profile_writes, [],
            "chưa có route sửa hồ sơ; nếu thêm thì phải có allowlist trường",
        )

    def test_oauth_exchange_only_creates_never_overwrites(self):
        """
        `/api/auth/oauth/exchange` nam trong allowlist o tren, nen phai chung
        minh no that su vo hai — neu khong, allowlist chi la mot cach lam ngo
        test.

        Nguoi dang nhap bang Google khong di qua `/api/auth/register` nen ho
        chua co ho so; route nay lap cho do. Cai KHONG duoc phep la ghi de:
        nguoi dung doi ten hien thi trong Fanfic roi mot thang sau dang nhap
        bang Google khong duoc bi Google dat lai ten ho, va `tier` thi khong
        bao gio duoc client quyet dinh.
        """
        import inspect

        from server import main as server_main
        from server.appwrite_adapter import AppwriteIdentityAdapter

        nguon_route = inspect.getsource(server_main.oauth_exchange)
        # Route khong tu cham kho: no uy quyen cho adapter.
        for cam in ("store.", "tier", "quota"):
            self.assertNotIn(cam, nguon_route,
                             f"route exchange khong duoc cham {cam!r}")

        nguon = inspect.getsource(AppwriteIdentityAdapter.ensure_profile)
        # TIM truoc roi moi TAO.
        self.assertIn('self._request("GET", path)', nguon)
        self.assertIn('"POST"', nguon)
        # Va tuyet doi khong sua ban ghi da co.
        for cam in ('"PATCH"', '"PUT"', '"DELETE"'):
            self.assertNotIn(cam, nguon,
                             f"ensure_profile khong duoc dung {cam}")
        # Ban ghi moi phai dung quyen chi-doc y nhu dang ky thuong.
        self.assertIn("profile_permissions(profile.user_id)", nguon)

    def test_logout_does_not_touch_profile_data(self):
        """
        `/api/auth/logout` nam trong allowlist o tren, nen phai chung minh no
        that su vo hai — neu khong, allowlist chi la mot cach lam ngo test.

        Dang xuat chi duoc cham toi SESSION. Mot lan cham vao `profiles` o day
        la duong cho client tu sua `tier` hoac bo dem quota.
        """
        import inspect

        from server import main as server_main
        from server.appwrite_adapter import AppwriteIdentityAdapter

        nguon_route = inspect.getsource(server_main.logout)
        for cam in ("store.", "profiles", "tier", "quota"):
            self.assertNotIn(cam, nguon_route,
                             f"route logout khong duoc cham {cam!r}")

        nguon_adapter = inspect.getsource(AppwriteIdentityAdapter.logout)
        self.assertIn("/v1/account/sessions", nguon_adapter)
        self.assertNotIn("collections", nguon_adapter,
                         "logout khong duoc ghi vao collection nao")

    def test_register_writes_profile_with_read_only_permissions(self):
        """Ban ghi ho so luc dang ky phai dung quyen chi-doc."""
        import inspect

        from server import appwrite_adapter

        source = inspect.getsource(appwrite_adapter.AppwriteIdentityAdapter.register)
        self.assertIn("profile_permissions(user_id)", source)
        self.assertNotIn('update("user:', source)
        self.assertNotIn('delete("user:', source)


class TestPermissionStringsAreWellFormed(unittest.TestCase):
    """Cu phap phai dung dinh dang Appwrite chap nhan."""

    PATTERN = re.compile(r'^(read|create|update|delete)\("(any|users|user:[^"]+)"\)$')

    def _all_permission_sets(self):
        yield profile_permissions(USER)
        yield AppwriteMetadataStore._owner_permissions(USER)
        yield AppwriteMetadataStore._owner_permissions(USER, public_read=True)

    def test_every_permission_string_is_well_formed(self):
        for permissions in self._all_permission_sets():
            for permission in permissions:
                self.assertRegex(permission, self.PATTERN)

    def test_no_duplicate_permissions(self):
        for permissions in self._all_permission_sets():
            self.assertEqual(len(permissions), len(set(permissions)))


class TestNoRegressionInBackendWrites(unittest.TestCase):
    """Bo `update`/`delete` khong duoc lam hong thao tac ghi cua backend."""

    def test_backend_still_updates_documents_with_the_api_key(self):
        """
        API key bo qua document permission, nen backend van PATCH duoc.

        Dung client gia lap - khong cham mang.
        """
        calls: List[Dict[str, Any]] = []

        class _Fake:
            def request(self, method, url, json=None, params=None, headers=None):
                calls.append({"method": method, "headers": headers, "payload": json})
                if method == "GET":
                    return {"novel_id": "nov_1", "owner_id": USER, "title": "T",
                            "state": "draft", "tags": [],
                            "created_at": "2026-08-06T00:00:00+00:00",
                            "updated_at": "2026-08-06T00:00:00+00:00"}
                return {}

        store = AppwriteMetadataStore(
            AppwriteSettings(endpoint="https://khong-co-that.example/v1",
                             project_id="gia", api_key="khoa-gia", database_id="db-gia"),
            client=_Fake(),
        )
        novel = store.publish_novel("nov_1", USER)

        self.assertEqual(novel.state.value, "published")
        patch = [c for c in calls if c["method"] == "PATCH"][0]
        self.assertIn("X-Appwrite-Key", patch["headers"],
                      "backend phải dùng API key, thứ bỏ qua document permission")
        self.assertEqual(patch["payload"]["data"]["state"], "published")


if __name__ == "__main__":
    unittest.main(verbosity=2)
