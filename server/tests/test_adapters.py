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


if __name__ == "__main__":
    unittest.main(verbosity=2)
