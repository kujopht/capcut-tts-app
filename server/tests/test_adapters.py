"""
Test cho adapter that (Appwrite / R2) - chay HOAN TOAN offline.

Khong goi Appwrite hay R2 that: chi kiem tra logic chon adapter, phat hien
cau hinh sai, va nguyen tac "khong am tham lui ve mock".
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from server.adapters import (
    LocalStorageAdapter,
    MockIdentityAdapter,
    NotFoundError,
    build_identity,
    build_storage,
)
from server.config import AppwriteSettings, R2Settings, Settings


def _settings(**kwargs) -> Settings:
    base = {"environment": "development", "var_dir": Path(tempfile.mkdtemp())}
    base.update(kwargs)
    return Settings(**base)


class TestAdapterSelection(unittest.TestCase):
    def test_mock_is_the_default(self):
        settings = _settings()
        settings.validate()
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)
        self.assertIsInstance(build_storage(settings), LocalStorageAdapter)
        self.assertEqual(settings.data_backend, "mock")
        self.assertEqual(settings.storage_backend, "local")

    def test_credentials_alone_do_not_switch_backend(self):
        """Co credential nhung khong chon che do -> VAN la mock (tuong minh)."""
        settings = _settings(appwrite=AppwriteSettings(
            endpoint="https://x/v1", project_id="p", api_key="k", database_id="d",
        ))
        settings.validate()
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)

    def test_partial_appwrite_config_stays_mock(self):
        """Thieu mot bien -> coi nhu chua cau hinh, khong nua voi."""
        settings = _settings(appwrite=AppwriteSettings(
            endpoint="https://x/v1", project_id="p", api_key="k",  # thieu database_id
        ))
        self.assertFalse(settings.appwrite.configured)
        self.assertIsInstance(build_identity(settings), MockIdentityAdapter)

    def test_partial_r2_config_stays_mock(self):
        settings = _settings(r2=R2Settings(
            account_id="a", access_key_id="k", secret_access_key="s",  # thieu bucket
        ))
        self.assertFalse(settings.r2.configured)
        self.assertIsInstance(build_storage(settings), LocalStorageAdapter)

    def test_appwrite_mode_with_bad_endpoint_fails_fast(self):
        """Chon che do appwrite ma cau hinh sai thi BAO LOI, khong lui ve mock."""
        settings = _settings(data_backend="appwrite", appwrite=AppwriteSettings(
            endpoint="khong-phai-url", project_id="p", api_key="k", database_id="d",
        ))
        from server.appwrite_adapter import AppwriteConfigError

        with self.assertRaises(AppwriteConfigError):
            build_identity(settings)

    def test_appwrite_mode_without_config_fails_fast(self):
        from server.config import ConfigError

        settings = _settings(data_backend="appwrite")
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        self.assertIn("APPWRITE_ENDPOINT", str(ctx.exception))

    def test_r2_mode_without_config_fails_fast(self):
        from server.config import ConfigError

        settings = _settings(storage_backend="r2")
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        self.assertIn("R2_ACCOUNT_ID", str(ctx.exception))

    def test_unknown_backend_rejected(self):
        from server.config import ConfigError

        with self.assertRaises(ConfigError):
            _settings(data_backend="postgres").validate()
        with self.assertRaises(ConfigError):
            _settings(storage_backend="s3").validate()

    def test_production_rejects_cors_wildcard(self):
        from server.config import ConfigError

        settings = _settings(environment="production", cors_origins=["*"])
        with self.assertRaises(ConfigError) as ctx:
            settings.validate()
        self.assertIn("wildcard", str(ctx.exception).lower())

    def test_r2_mode_never_falls_back_to_local(self):
        settings = _settings(storage_backend="r2", r2=R2Settings(
            account_id="acc", access_key_id="k", secret_access_key="s", bucket="b",
        ))
        settings.validate()
        from server.r2_adapter import R2ConfigError

        try:
            adapter = build_storage(settings)
        except R2ConfigError:
            return          # chua cai boto3 -> bao loi ro, dung nhu thiet ke
        self.assertEqual(adapter.mode, "r2")
        self.assertNotIsInstance(adapter, LocalStorageAdapter)

    def test_r2_endpoint_is_derived_not_hardcoded(self):
        r2 = R2Settings(account_id="abc123", access_key_id="k",
                        secret_access_key="s", bucket="b")
        self.assertEqual(r2.endpoint_url, "https://abc123.r2.cloudflarestorage.com")

    def test_settings_describe_never_leaks_secrets(self):
        settings = _settings(
            appwrite=AppwriteSettings(endpoint="https://x/v1", project_id="p",
                                      api_key="BIMAT", database_id="d"),
            r2=R2Settings(account_id="a", access_key_id="KHOABIMAT",
                          secret_access_key="RATBIMAT", bucket="b"),
        )
        text = str(settings.describe())
        for secret in ("BIMAT", "KHOABIMAT", "RATBIMAT"):
            self.assertNotIn(secret, text)


class TestLocalStorage(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.storage = LocalStorageAdapter(self.root)

    def test_put_and_get(self):
        self.storage.put("audio/u1/c1/x.mp3", b"\x00" * 2048)
        self.assertEqual(len(self.storage.get("audio/u1/c1/x.mp3")), 2048)
        self.assertTrue(self.storage.exists("audio/u1/c1/x.mp3"))
        self.assertEqual(self.storage.size("audio/u1/c1/x.mp3"), 2048)

    def test_missing_key_raises(self):
        with self.assertRaises(NotFoundError):
            self.storage.get("khong/co.mp3")

    def test_path_traversal_blocked(self):
        with self.assertRaises(ValueError):
            self.storage.put("../../thoat.mp3", b"x")

    def test_no_partial_file_left_behind(self):
        self.storage.put("a/b.mp3", b"\x00" * 512)
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_local_has_no_signed_url(self):
        """Ban cuc bo tra None de tang tren biet phai stream qua backend."""
        self.assertIsNone(self.storage.signed_url("a/b.mp3"))


class TestAppwriteAdapterGuards(unittest.TestCase):
    def test_incomplete_config_rejected(self):
        from server.appwrite_adapter import AppwriteConfigError, AppwriteIdentityAdapter

        with self.assertRaises(AppwriteConfigError):
            AppwriteIdentityAdapter(AppwriteSettings())

    def test_bad_endpoint_rejected_with_clear_message(self):
        from server.appwrite_adapter import AppwriteConfigError, AppwriteIdentityAdapter

        with self.assertRaises(AppwriteConfigError) as ctx:
            AppwriteIdentityAdapter(AppwriteSettings(
                endpoint="ftp://sai", project_id="p", api_key="k", database_id="d",
            ))
        self.assertIn("http", str(ctx.exception).lower())

    def test_api_key_only_in_server_headers(self):
        """API key chi duoc gan o header phia server, khong lot ra cho khac."""
        from server.appwrite_adapter import AppwriteIdentityAdapter

        adapter = AppwriteIdentityAdapter(AppwriteSettings(
            endpoint="https://example.test/v1", project_id="p",
            api_key="SIEUBIMAT", database_id="d",
        ))
        admin = adapter._headers(admin=True)
        self.assertEqual(admin["X-Appwrite-Key"], "SIEUBIMAT")

        # Khi dung session cua nguoi dung thi TUYET DOI khong gui API key.
        # Appwrite tu choi request vua co API key vua co danh tinh nguoi dung,
        # va quan trong hon: request do phai chay dung quyen cua nguoi dung.
        with_session = adapter._headers(session="session-cua-nguoi-dung")
        self.assertNotIn("X-Appwrite-Key", with_session)
        self.assertEqual(with_session["X-Appwrite-Session"], "session-cua-nguoi-dung")
        self.assertNotIn("X-Appwrite-JWT", with_session,
                         "session secret khong phai JWT - gui nhầm header thì Appwrite từ chối")


class TestR2AdapterGuards(unittest.TestCase):
    def test_incomplete_config_rejected(self):
        from server.r2_adapter import R2ConfigError, R2StorageAdapter

        with self.assertRaises(R2ConfigError):
            R2StorageAdapter(R2Settings())

    def test_missing_boto3_reports_clearly(self):
        """Da cau hinh R2 ma thieu boto3 thi phai noi ro cach khac phuc."""
        import importlib.util

        if importlib.util.find_spec("boto3") is not None:
            self.skipTest("boto3 đã được cài")
        from server.r2_adapter import R2ConfigError, R2StorageAdapter

        with self.assertRaises(R2ConfigError) as ctx:
            R2StorageAdapter(R2Settings(account_id="a", access_key_id="k",
                                        secret_access_key="s", bucket="b"))
        self.assertIn("boto3", str(ctx.exception))


class TestR2AdapterProbes(unittest.TestCase):
    """
    Bon ham `*_probe` (chi phuc vu `/api/admin/_diag/r2-probe`, su co
    2026-08-23: PUT bao thanh cong nhung HEAD/GET ngay sau lai bao
    `NoSuchKey`). Khac `put()`/`get()` binh thuong (vut bo response cua
    boto3), cac ham nay phai lay duoc METADATA THAT — va KHONG BAO GIO nem
    loi ra ngoai, ke ca khi object khong ton tai.
    """

    def _adapter(self):
        from server.r2_adapter import R2StorageAdapter

        return R2StorageAdapter(R2Settings(
            account_id="acc123", access_key_id="k", secret_access_key="s",
            bucket="qa-bucket"))

    def test_put_probe_tra_ve_metadata_that(self):
        adapter = self._adapter()

        class FakeClient:
            def put_object(self, **kw):
                return {"ETag": '"abc123"',
                       "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-1"}}

        adapter._client = FakeClient()
        r = adapter.put_probe("k.txt", b"data")
        self.assertEqual(r["http_status"], 200)
        self.assertEqual(r["request_id"], "req-1")
        self.assertEqual(r["etag"], '"abc123"')

    def test_head_probe_khong_ton_tai_khong_nem_loi(self):
        adapter = self._adapter()

        class LoiKhongTonTai(Exception):
            def __init__(self):
                super().__init__("khong tim thay")
                self.response = {
                    "Error": {"Code": "NoSuchKey",
                             "Message": "The specified key does not exist."},
                    "ResponseMetadata": {"HTTPStatusCode": 404, "RequestId": "req-2"},
                }

        class FakeClient:
            def head_object(self, **kw):
                raise LoiKhongTonTai()

        adapter._client = FakeClient()
        r = adapter.head_probe("k.txt")
        self.assertFalse(r["tim_thay"])
        self.assertEqual(r["ma_loi"], "NoSuchKey")
        self.assertEqual(r["http_status"], 404)
        self.assertEqual(r["request_id"], "req-2")

    def test_head_probe_ton_tai_tra_metadata(self):
        adapter = self._adapter()

        class FakeClient:
            def head_object(self, **kw):
                return {"ETag": '"xyz"', "ContentLength": 1234,
                       "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-3"}}

        adapter._client = FakeClient()
        r = adapter.head_probe("k.txt")
        self.assertTrue(r["tim_thay"])
        self.assertEqual(r["content_length"], 1234)
        self.assertEqual(r["etag"], '"xyz"')

    def test_get_probe_doc_dung_so_byte(self):
        adapter = self._adapter()

        class FakeBody:
            def read(self):
                return b"hello world"

        class FakeClient:
            def get_object(self, **kw):
                return {"Body": FakeBody(), "ETag": '"e"',
                       "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-4"}}

        adapter._client = FakeClient()
        r = adapter.get_probe("k.txt")
        self.assertTrue(r["tim_thay"])
        self.assertEqual(r["so_byte_doc_duoc"], 11)

    def test_list_probe_tra_danh_sach_khoa(self):
        adapter = self._adapter()

        class FakeClient:
            def list_objects_v2(self, **kw):
                return {"KeyCount": 2, "Contents": [{"Key": "a"}, {"Key": "b"}],
                       "ResponseMetadata": {"HTTPStatusCode": 200, "RequestId": "req-5"}}

        adapter._client = FakeClient()
        r = adapter.list_probe("prefix/")
        self.assertEqual(r["so_khoa"], 2)
        self.assertEqual(r["khoa"], ["a", "b"])

    def test_khong_bao_gio_chua_thong_tin_bi_mat(self):
        """
        Loi tu boto3 co the mang theo `HTTPHeaders` trong `ResponseMetadata`
        — voi request da ky SigV4, header do CHUA access key id trong
        `Authorization`. Dam bao `_loi_thanh_dict` CHI lay nhung truong
        duoc chon ro rang, khong bao gio ca `ResponseMetadata`/`response` goc.
        """
        adapter = self._adapter()

        class LoiCoContextNhay(Exception):
            def __init__(self):
                super().__init__("tu choi")
                self.response = {
                    "Error": {"Code": "AccessDenied", "Message": "loi"},
                    "ResponseMetadata": {
                        "HTTPStatusCode": 403, "RequestId": "req-6",
                        "HTTPHeaders": {
                            "authorization":
                                "AWS4-HMAC-SHA256 Credential=BI-MAT-KHONG-DUOC-LO/...",
                        },
                    },
                }

        class FakeClient:
            def head_object(self, **kw):
                raise LoiCoContextNhay()

        adapter._client = FakeClient()
        r = adapter.head_probe("k.txt")
        self.assertNotIn("HTTPHeaders", r)
        chuoi = str(r)
        self.assertNotIn("authorization", chuoi)
        self.assertNotIn("BI-MAT-KHONG-DUOC-LO", chuoi)


class TestR2AdapterPutFile(unittest.TestCase):
    """
    `put_file` PHAI STREAM tu dia (dung `upload_file` cua boto3 — tu chuyen
    sang multipart khi file lon), KHONG doc het file vao RAM roi moi goi
    `put_object`. File audio import sap toi co the toi ~2GB (dai toi 63 gio),
    nen doc het vao bo nho truoc la mot dinh RAM khong can thiet.
    """

    def _adapter(self):
        from server.r2_adapter import R2StorageAdapter

        return R2StorageAdapter(R2Settings(
            account_id="acc123", access_key_id="k", secret_access_key="s",
            bucket="qa-bucket"))

    def test_put_file_dung_upload_file_khong_doc_het_vao_ram(self):
        adapter = self._adapter()

        with tempfile.TemporaryDirectory() as tmp:
            nguon = Path(tmp) / "track.mp3"
            nguon.write_bytes(b"gia-lap-noi-dung-audio")

            class FakeClient:
                def __init__(self):
                    self.upload_file_calls = []
                    self.put_object_calls = []

                def upload_file(self, filename, bucket, key, ExtraArgs=None):
                    self.upload_file_calls.append((filename, bucket, key, ExtraArgs))

                def put_object(self, **kw):
                    # KHONG duoc goi duong nay — do la duong `put()` doc het
                    # vao RAM, chinh la thu put_file phai tranh.
                    self.put_object_calls.append(kw)
                    return {}

            fake = FakeClient()
            adapter._client = fake

            key = adapter.put_file("audio/k.mp3", nguon)

            self.assertEqual(key, "audio/k.mp3")
            self.assertEqual(len(fake.upload_file_calls), 1)
            self.assertEqual(len(fake.put_object_calls), 0)
            filename, bucket, sent_key, extra_args = fake.upload_file_calls[0]
            self.assertEqual(filename, str(nguon))
            self.assertEqual(bucket, "qa-bucket")
            self.assertEqual(sent_key, "audio/k.mp3")
            self.assertEqual(extra_args, {"ContentType": "audio/mpeg"})

class TestProfileFromRow(unittest.TestCase):
    """
    `_profile_from` (hang `profiles` -> `Profile`) la nguon cho MOI duong doc
    NHIEU ho so mot luot (`profiles_by_ids`, `profile_by_username`, tim kiem).

    Bo BUG THAT: ham nay da doc `username`/`bio`/`author_status` nhung QUEN
    `avatar_key` khi truong do duoc them — hau qua la avatar bien mat khoi
    bai dang/binh luan/thong bao/tim kiem (tat ca di qua duong nay) trong khi
    van hien dung o `/api/auth/me` (di qua `_merge_stored`, mot ham khac).
    """

    def test_avatar_key_duoc_doc_tu_hang(self):
        from server.appwrite_adapter import _profile_from

        p = _profile_from({
            "user_id": "u1", "email": "a@vidu.vn", "username": "an",
            "bio": "chao", "author_status": "approved",
            "avatar_key": "avatars/u1/anh.webp",
        })
        self.assertEqual(p.avatar_key, "avatars/u1/anh.webp")

    def test_thieu_avatar_key_tra_chuoi_rong_khong_nem(self):
        from server.appwrite_adapter import _profile_from

        p = _profile_from({"user_id": "u1", "email": "a@vidu.vn"})
        self.assertEqual(p.avatar_key, "")

    HANG_SOCIAL_V1 = {
        "user_id": "u1", "email": "a@vidu.vn", "username": "an",
        "banner_key": "banners/u1/b.webp", "accent": "jade",
        "fandom_ids": ["naruto", "one-piece"],
    }

    def test_truong_social_v1_duoc_doc_tu_hang(self):
        """Do that tren Appwrite 1.9.6 THU (2026-09-26): ghi dung ca ba truong
        vao hang, nhung ho so cong khai tra `accent: null`, `fandom_ids: []`,
        khong banner — `_profile_from` tung quen ca ba (cung loai voi avatar_key)."""
        from server.appwrite_adapter import _profile_from

        p = _profile_from(dict(self.HANG_SOCIAL_V1))
        self.assertEqual((p.banner_key, p.accent, p.fandom_ids),
                         ("banners/u1/b.webp", "jade", ["naruto", "one-piece"]))

    def test_truong_social_v1_thieu_tra_rong_khong_nem(self):
        from server.appwrite_adapter import _profile_from

        p = _profile_from({"user_id": "u1", "email": "a@vidu.vn", "fandom_ids": None})
        self.assertEqual((p.banner_key, p.accent, p.fandom_ids), ("", "", []))

    def test_merge_stored_cung_doc_truong_social_v1(self):
        """Duong THU HAI (`/api/auth/me` -> `_merge_stored`) phai doc cung ba
        truong — hai duong doc tung lech nhau o `avatar_key`."""
        from unittest.mock import patch

        from server.appwrite_adapter import AppwriteIdentityAdapter
        from server.domain import Profile

        adapter = AppwriteIdentityAdapter(AppwriteSettings(
            endpoint="https://x.invalid/v1", project_id="p", api_key="k", database_id="db"))
        with patch.object(adapter, "_request", return_value=dict(self.HANG_SOCIAL_V1)):
            p = adapter._merge_stored(Profile(user_id="u1", email="a@vidu.vn"))
        self.assertEqual((p.banner_key, p.accent, p.fandom_ids),
                         ("banners/u1/b.webp", "jade", ["naruto", "one-piece"]))


class TestLoi5xxAppwriteKhongThanh401(unittest.TestCase):
    """Do that (Appwrite 1.9.6 + MongoDB THU, 2026-09-26): 6 request DONG THOI cua cung
    mot nguoi -> 3 lan `GET /v1/account` tra 500 "Transaction aborted", va backend tra
    401 cho nguoi dung dang dang nhap hop le (giao dien coi 401 la het phien)."""

    class _ClientGia:
        def __init__(self, codes):
            import httpx as _httpx

            self._httpx = _httpx
            self.codes = list(codes)
            self.goi = 0
            self.cookies = type("C", (), {"clear": lambda self: None})()

        def request(self, method, url, **kw):
            self.goi += 1
            code = self.codes.pop(0)
            body = ({"$id": "u1", "email": "a@vidu.vn", "name": "An"} if code == 200
                    else {"message": "Transaction aborted", "code": code})
            return self._httpx.Response(code, json=body, request=self._httpx.Request(method, url))

    def _adapter(self, codes):
        from unittest.mock import patch

        from server.appwrite_adapter import AppwriteIdentityAdapter

        adapter = AppwriteIdentityAdapter(AppwriteSettings(
            endpoint="https://x.invalid/v1", project_id="p", api_key="k", database_id="db"))
        gia = self._ClientGia(codes)
        patch.object(adapter, "_http", return_value=gia).start()
        patch.object(adapter, "_merge_stored", side_effect=lambda p: p).start()
        patch("server.appwrite_adapter.time.sleep", return_value=None).start()
        self.addCleanup(patch.stopall)
        return adapter, gia

    def test_5xx_la_appwrite_unavailable_khong_phai_loi_dang_nhap(self):
        from server.adapters import AppwriteUnavailableError

        adapter, _ = self._adapter([500])
        with self.assertRaises(AppwriteUnavailableError):
            adapter._request("GET", "/v1/account", session="s", admin=False)

    def test_401_van_la_loi_dang_nhap(self):
        from server.adapters import AppwriteUnavailableError, AuthError

        adapter, _ = self._adapter([401])
        with self.assertRaises(AuthError) as ctx:
            adapter._request("GET", "/v1/account", session="s", admin=False)
        self.assertNotIsInstance(ctx.exception, AppwriteUnavailableError)

    def test_xac_minh_phien_thu_lai_khi_500_thoang_qua(self):
        adapter, gia = self._adapter([500, 200])
        p = adapter.profile_from_token("s")
        self.assertEqual((p.user_id, gia.goi), ("u1", 2))

    def test_xac_minh_phien_500_mai_thi_503_sau_ba_lan(self):
        from server.adapters import AppwriteUnavailableError

        adapter, gia = self._adapter([500, 500, 500])
        with self.assertRaises(AppwriteUnavailableError):
            adapter.profile_from_token("s")
        self.assertEqual(gia.goi, 3)

    def test_phien_sai_khong_thu_lai(self):
        from server.adapters import AuthError

        adapter, gia = self._adapter([401])
        with self.assertRaises(AuthError):
            adapter.profile_from_token("s")
        self.assertEqual(gia.goi, 1)

    def test_timeout_khong_thu_lai(self):
        """Review doc lap: thu lai ca timeout (15 s/lan) giu request toi ~45 s khi Appwrite treo."""
        import httpx

        from server.adapters import AppwriteUnavailableError

        adapter, gia = self._adapter([])
        goi = {"n": 0}

        def treo(method, url, **kw):
            goi["n"] += 1
            raise httpx.ReadTimeout("timed out")

        gia.request = treo
        with self.assertRaises(AppwriteUnavailableError):
            adapter.profile_from_token("s")
        self.assertEqual(goi["n"], 1)

    def test_5xx_khong_lo_loi_noi_bo_appwrite(self):
        from server.adapters import AppwriteUnavailableError

        adapter, _ = self._adapter([500, 500, 500])
        with self.assertRaises(AppwriteUnavailableError) as ctx:
            adapter.profile_from_token("s")
        self.assertNotIn("Transaction", str(ctx.exception))


class TestSaveProfileDatetimeCoercion(unittest.TestCase):
    """
    Kiem tra thu hoach TU dot Appwrite optional-datetime audit (sau Phase 6):
    Appwrite (tu luu tru) tu dien gio server HIEN TAI cho mot thuoc tinh
    `datetime` KHONG bat buoc khi nhan chuoi rong "", thay vi null nhu ky
    vong (xem `appwrite_trusted_source_store.py::_DATETIME_FIELDS`).

    `save_profile` (PATCH mot ho so DA CO) tung xay dung payload bang
    `getattr(profile, k)` THO, KHONG qua `Profile.to_dict()` (von da tu
    doi "" -> None cho ba truong nay) — moi lan goi (vd chi doi bio/avatar)
    ma nguoi dung CHUA tung doc/nghe/xem gi se ghi de `last_read_at`/
    `last_listen_at`/`last_watch_at` thanh CHUOI RONG, kich hoat dung tat
    Appwrite noi tren.
    """

    def _adapter_gia_lap(self):
        from server.appwrite_adapter import AppwriteIdentityAdapter

        adapter = AppwriteIdentityAdapter(AppwriteSettings(
            endpoint="https://x.invalid/v1", project_id="p",
            api_key="k", database_id="db"))
        # Gia lap ket qua da hoi schema MOT LAN (tranh goi mang that) — MOI
        # thuoc tinh V2 coi nhu da co tren Appwrite.
        adapter._profile_attrs = set(adapter._PROFILE_V2_FIELDS) | {"username"}
        return adapter

    def test_ho_so_chua_doc_nghe_xem_gi_ghi_null_khong_phai_chuoi_rong(self):
        from server.domain import Profile

        adapter = self._adapter_gia_lap()
        captured = {}

        def gia_request(method, path, *, payload=None, params=None,
                        session="", admin=True):
            captured["payload"] = payload
            return {}

        adapter._request = gia_request
        profile = Profile(user_id="u1", email="a@vidu.vn", username="an")
        adapter.save_profile(profile)

        data = captured["payload"]["data"]
        self.assertIsNone(data["last_read_at"])
        self.assertIsNone(data["last_listen_at"])
        self.assertIsNone(data["last_watch_at"])

    def test_ho_so_da_co_moc_thoi_gian_that_van_giu_nguyen(self):
        from server.domain import Profile

        adapter = self._adapter_gia_lap()
        captured = {}

        def gia_request(method, path, *, payload=None, params=None,
                        session="", admin=True):
            captured["payload"] = payload
            return {}

        adapter._request = gia_request
        profile = Profile(user_id="u1", email="a@vidu.vn", username="an",
                          last_read_at="2026-01-01T00:00:00+00:00")
        adapter.save_profile(profile)

        data = captured["payload"]["data"]
        self.assertEqual(data["last_read_at"], "2026-01-01T00:00:00+00:00")
        self.assertIsNone(data["last_listen_at"])
        self.assertIsNone(data["last_watch_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
